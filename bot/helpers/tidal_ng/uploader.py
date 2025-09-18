import os
import shutil
import asyncio
import re
from config import Config
from bot.logger import LOGGER
from bot.settings import bot_set
from bot.helpers.utils import format_string, send_message, edit_message, MAX_SIZE
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from ..state import conversation_state


async def _get_tidal_ng_base_path(user_id: int) -> str:
    return os.path.join(Config.LOCAL_STORAGE, str(user_id), "Tidal_NG")


def _get_folder_size(folder_path: str) -> int:
    total_size = 0
    for root, _, files in os.walk(folder_path):
        for f in files:
            try:
                total_size += os.path.getsize(os.path.join(root, f))
            except Exception:
                continue
    return total_size


async def create_tidal_ng_zip(directory: str, user_id: int, metadata: dict) -> str:
    """Create a zip file for Tidal NG content with provider-aware naming.

    Examples:
    - Album:     [Tidal NG] The_Album_Name.zip
    - Playlist:  [Tidal NG] My_Playlist (Playlist).zip
    - Artist:    [Tidal NG] Some_Artist (Artist).zip
    - Video:     [Tidal NG] Some_Video (Video).zip
    """
    title = (metadata.get('title') or 'Tidal NG').strip()
    # sanitize and convert spaces to underscores similar to Apple helper
    safe_title = re.sub(r'[\\/*?:"<>|]', '', title)
    if bot_set.zip_name_use_underscores:
        safe_title = safe_title.replace(' ', '_')
    provider = 'Tidal NG'
    ctype = (metadata.get('type') or 'album').strip().lower()

    if ctype == 'album':
        base = f"[{provider}] {safe_title}"
    elif ctype == 'playlist':
        base = f"[{provider}] {safe_title} (Playlist)"
    elif ctype == 'artist':
        base = f"[{provider}] {safe_title} (Artist)"
    elif ctype == 'video':
        base = f"[{provider}] {safe_title} (Video)"
    else:
        base = f"[{provider}] {safe_title}"

    zip_dir = os.path.dirname(directory)
    zip_path = os.path.join(zip_dir, f"{base}.zip")
    idx = 1
    while os.path.exists(zip_path):
        zip_path = os.path.join(zip_dir, f"{base}_{idx}.zip")
        idx += 1
    # Simple synchronous zipping (folder small enough or split handled elsewhere)
    import zipfile
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, _, files in os.walk(directory):
            for f in files:
                fp = os.path.join(root, f)
                arc = os.path.relpath(fp, directory)
                zipf.write(fp, arc)
    LOGGER.info(f"Created Tidal NG zip: {zip_path}")
    return zip_path


async def _rclone_upload(user, path, base_path, quality: str | None = None):
    """
    Uploads files/folders to Rclone with quality-based subdirectories.
    - Fixes single track uploads.
    - Adds quality subfolder.
    - Adds verbose logging.
    """
    dest_root = (getattr(bot_set, 'rclone_dest', None) or Config.RCLONE_DEST)
    if not dest_root:
        return None, None, None

    abs_path = os.path.abspath(path)
    is_dir = os.path.isdir(abs_path)

    # Calculate relative path from the base download directory
    try:
        base_abs = os.path.abspath(base_path)
        rel_path = os.path.relpath(abs_path, base_abs) if abs_path.startswith(base_abs) else os.path.basename(abs_path)
    except Exception:
        rel_path = os.path.basename(abs_path)

    # Prepend quality folder if quality is provided
    if quality:
        # Sanitize quality string for use as a folder name
        safe_quality = quality.replace(" ", "_").replace("/", "_")
        final_rel_path = os.path.join(safe_quality, rel_path)
    else:
        final_rel_path = rel_path

    # Correctly determine source and destination for rclone
    if is_dir:
        # If path is a directory, copy the directory itself.
        source_for_copy = abs_path
        # The destination is the remote path including the new quality folder.
        dest_path = f"{dest_root}/{os.path.dirname(final_rel_path)}".rstrip('/')
    else:
        # If path is a single file, copy the file's parent directory
        # but use --include to only upload the single file. This preserves structure.
        source_for_copy = os.path.dirname(abs_path)
        # The destination is the remote path including the new quality folder and subfolders.
        dest_path = f"{dest_root}/{os.path.dirname(final_rel_path)}".rstrip('/')

    # Add verbose flag and include filter for single files
    copy_cmd = f'rclone copy -v --config ./rclone.conf "{source_for_copy}" "{dest_path}"'
    if not is_dir:
        # Ensure we only copy the intended file, not everything in the source directory
        file_name = os.path.basename(abs_path)
        copy_cmd += f" --include \"{file_name}\""


    proc = await asyncio.create_subprocess_shell(
        copy_cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    out, err = await proc.communicate()
    if proc.returncode != 0:
        LOGGER.error(f"Rclone copy failed for '{source_for_copy}'.\nCMD: {copy_cmd}\nOutput:\n{err.decode().strip()}")
        return None, None, None

    # Link generation needs to use the final relative path
    rclone_link = None
    index_link = None
    if bot_set.link_options in ['RCLONE', 'Both']:
        link_target = f"{dest_root}/{final_rel_path}".rstrip('/')
        link_cmd = f'rclone link --config ./rclone.conf "{link_target}"'
        t2 = await asyncio.create_subprocess_shell(
            link_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        so, se = await t2.communicate()
        if t2.returncode == 0:
            rclone_link = so.decode().strip()
    if bot_set.link_options in ['Index', 'Both'] and Config.INDEX_LINK:
        index_link = f"{Config.INDEX_LINK}/{final_rel_path}".replace(' ', '%20')

    # remote_info for the manage button must also use the final path
    remote = ''
    base = ''
    try:
        if dest_root and ':' in dest_root:
            remote, base = dest_root.split(':', 1)
            base = base.strip('/')
        else:
            remote = (getattr(bot_set, 'rclone_remote', '') or dest_root or '').rstrip(':')
    except Exception:
        remote = ''

    info = {
        'remote': remote,
        'base': base,
        'path': final_rel_path,
        'is_dir': is_dir
    }
    return rclone_link, index_link, info


async def _post_manage(user, remote_info: dict):
    """Posts a message with a button to manage the uploaded content via Rclone."""
    try:
        from ..database.pg_impl import rclone_sessions_db
        import uuid

        token = uuid.uuid4().hex[:10]
        rel_path = remote_info.get('path') or ''
        is_dir = bool(remote_info.get('is_dir'))

        if is_dir:
            src_path = rel_path
            src_file = None
        else:
            src_path = os.path.dirname(rel_path)
            src_file = rel_path

        context = {
            'src_remote': remote_info.get('remote'),
            'base': remote_info.get('base'),
            'src_path': src_path,
            'src_file': src_file,
            'dst_remote': None,
            'dst_path': '',
            'cc_mode': 'copy',
            'src_page': 0
        }

        rclone_sessions_db.add_session(
            token=token,
            user_id=user['user_id'],
            context=context
        )

        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📂 Browse uploaded (Copy/Move)", callback_data=f"rcloneManageStart|{token}")]
        ])
        await send_message(user, "Manage the uploaded item:", markup=kb)
    except Exception as e:
        LOGGER.error(f"Failed to create rclone manage button: {e}", exc_info=True)


async def track_upload(metadata, user, index: int = None, total: int = None):
    base_path = await _get_tidal_ng_base_path(user['user_id'])
    if bot_set.upload_mode == 'Telegram':
        reporter = user.get('progress')
        if reporter:
            try:
                await reporter.set_stage("Uploading")
            except Exception:
                pass
        await send_message(
            user,
            metadata['filepath'],
            'audio',
            caption=await format_string(
                "🎵 **{title}**\n👤 {artist}\n🎧 {provider}",
                {
                    'title': metadata['title'],
                    'artist': metadata['artist'],
                    'provider': metadata.get('provider', 'Tidal NG')
                }
            ),
            meta={
                'duration': metadata.get('duration', 0),
                'artist': metadata.get('artist', 'Unknown Artist'),
                'title': metadata.get('title', 'Unknown'),
                'thumbnail': metadata.get('thumbnail')
            },
            file_index=index,
            total_files=total,
        )
    else:
        quality = metadata.get('quality')
        r_link, i_link, info = await _rclone_upload(user, metadata['filepath'], base_path, quality=quality)
        text = await format_string(
            "🎵 **{title}**\n👤 {artist}\n🎧 {provider}\n🔗 [Direct Link]({r_link})",
            {
                'title': metadata['title'],
                'artist': metadata['artist'],
                'provider': metadata.get('provider', 'Tidal NG'),
                'r_link': r_link
            }
        )
        if i_link:
            text += f"\n📁 [Index Link]({i_link})"
        await send_message(user, text)
        await _post_manage(user, info)
    # Cleanup
    try:
        os.remove(metadata['filepath'])
    except Exception:
        pass
    if metadata.get('thumbnail'):
        try:
            os.remove(metadata['thumbnail'])
        except Exception:
            pass


async def music_video_upload(metadata, user):
    base_path = await _get_tidal_ng_base_path(user['user_id'])
    if bot_set.upload_mode == 'Telegram':
        send_type = 'doc' if getattr(bot_set, 'video_as_document', False) else 'video'
        await send_message(
            user,
            metadata['filepath'],
            send_type,
            caption=await format_string(
                "🎬 **{title}**\n👤 {artist}\n🎧 {provider} Music Video",
                {
                    'title': metadata['title'],
                    'artist': metadata['artist'],
                    'provider': metadata.get('provider', 'Tidal NG')
                }
            ),
            meta=metadata,
        )
    else:
        quality = metadata.get('quality')
        r_link, i_link, info = await _rclone_upload(user, metadata['filepath'], base_path, quality=quality)
        text = await format_string(
            "🎬 **{title}**\n👤 {artist}\n🎧 {provider} Music Video\n🔗 [Direct Link]({r_link})",
            {
                'title': metadata['title'],
                'artist': metadata['artist'],
                'provider': metadata.get('provider', 'Tidal NG'),
                'r_link': r_link
            }
        )
        if i_link:
            text += f"\n📁 [Index Link]({i_link})"
        await send_message(user, text)
        await _post_manage(user, info)
    # Cleanup
    try:
        os.remove(metadata['filepath'])
    except Exception:
        pass
    if metadata.get('thumbnail'):
        try:
            os.remove(metadata['thumbnail'])
        except Exception:
            pass


async def album_upload(metadata, user):
    base_path = await _get_tidal_ng_base_path(user['user_id'])
    if bot_set.upload_mode == 'Telegram':
        if getattr(bot_set, 'tidal_ng_album_zip', False):
            # Always create a single descriptive zip for Telegram mode
            zp = await create_tidal_ng_zip(metadata['folderpath'], user['user_id'], metadata)
            zip_paths = [zp]
            caption = await format_string(
                "💿 **{album}**\n👤 {artist}\n🎧 {provider}",
                {
                    'album': metadata['title'],
                    'artist': metadata['artist'],
                    'provider': metadata.get('provider', 'Tidal NG')
                }
            )
            for idx, zp in enumerate(zip_paths, start=1):
                await send_message(user, zp, 'doc', caption=caption)
                try:
                    os.remove(zp)
                except Exception:
                    pass
        else:
            tracks = metadata.get('tracks') or metadata.get('items', [])
            total_tracks = len(tracks)
            for idx, track in enumerate(tracks, start=1):
                await track_upload(track, user, index=idx, total=total_tracks)
    else:
        # For albums, get quality from the first track as a representative
        quality = None
        if metadata.get('items'):
            quality = metadata['items'][0].get('quality')
        r_link, i_link, info = await _rclone_upload(user, metadata['folderpath'], base_path, quality=quality)
        text = await format_string(
            "💿 **{album}**\n👤 {artist}\n🎧 {provider}\n🔗 [Direct Link]({r_link})",
            {
                'album': metadata['title'],
                'artist': metadata['artist'],
                'provider': metadata.get('provider', 'Tidal NG'),
                'r_link': r_link
            }
        )
        if i_link:
            text += f"\n📁 [Index Link]({i_link})"
        if metadata.get('poster_msg'):
            await edit_message(metadata['poster_msg'], text)
        else:
            await send_message(user, text)
        await _post_manage(user, info)
    # Cleanup
    shutil.rmtree(metadata['folderpath'])


async def playlist_upload(metadata, user):
    base_path = await _get_tidal_ng_base_path(user['user_id'])
    if bot_set.upload_mode == 'Telegram':
        if getattr(bot_set, 'tidal_ng_playlist_zip', False):
            zp = await create_tidal_ng_zip(metadata['folderpath'], user['user_id'], metadata)
            caption = await format_string(
                "🎵 **{title}**\n👤 Curated by {artist}\n🎧 {provider} Playlist",
                {
                    'title': metadata['title'],
                    'artist': metadata.get('artist', 'Various Artists'),
                    'provider': metadata.get('provider', 'Tidal NG')
                }
            )
            await send_message(user, zp, 'doc', caption=caption)
            try:
                os.remove(zp)
            except Exception:
                pass
        else:
            tracks = metadata.get('tracks') or metadata.get('items', [])
            total_tracks = len(tracks)
            for idx, track in enumerate(tracks, start=1):
                await track_upload(track, user, index=idx, total=total_tracks)
    else:
        # For playlists, get quality from the first track as a representative
        quality = None
        if metadata.get('items'):
            quality = metadata['items'][0].get('quality')
        r_link, i_link, info = await _rclone_upload(user, metadata['folderpath'], base_path, quality=quality)
        text = await format_string(
            "🎵 **{title}**\n👤 Curated by {artist}\n🎧 {provider} Playlist\n🔗 [Direct Link]({r_link})",
            {
                'title': metadata['title'],
                'artist': metadata.get('artist', 'Various Artists'),
                'provider': metadata.get('provider', 'Tidal NG'),
                'r_link': r_link
            }
        )
        if i_link:
            text += f"\n📁 [Index Link]({i_link})"
        await send_message(user, text)
        await _post_manage(user, info)
    # Cleanup
    shutil.rmtree(metadata['folderpath'])

