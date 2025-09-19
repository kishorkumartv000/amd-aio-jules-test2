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
    """Create a zip file for Tidal NG content with provider-aware naming."""
    title = (metadata.get('title') or 'Tidal NG').strip()
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

    import zipfile
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, _, files in os.walk(directory):
            for f in files:
                fp = os.path.join(root, f)
                arc = os.path.relpath(fp, directory)
                zipf.write(fp, arc)
    LOGGER.info(f"Created Tidal NG zip: {zip_path}")
    return zip_path


async def _rclone_upload(user, path, base_path):
    """
    Uploads files/folders to Rclone using the corrected logic from the Apple Music uploader.
    """
    dest_root = (getattr(bot_set, 'rclone_dest', None) or Config.RCLONE_DEST)
    if not dest_root:
        return None, None, None

    abs_path = os.path.abspath(path)
    is_dir = os.path.isdir(abs_path)

    def _compute_relative(p: str, base: str | None) -> str:
        try:
            p_abs = os.path.abspath(p)
            if base:
                base_abs = os.path.abspath(base)
                if p_abs.startswith(base_abs):
                    return os.path.normpath(os.path.relpath(p_abs, base_abs))
        except Exception:
            pass
        # Fallback for Tidal NG: try to anchor at a known subfolder
        for anchor in ["/Albums/", "/Playlists/", "/Tracks/", "/Videos/", "/Mix/"]:
            sep_anchor = anchor.replace("/", os.sep)
            if sep_anchor in p_abs:
                try:
                    root = p_abs.split(sep_anchor, 1)[0]
                    return os.path.normpath(os.path.relpath(p_abs, root))
                except Exception:
                    continue
        return os.path.basename(p_abs) if os.path.isfile(p_abs) else os.path.basename(os.path.normpath(p_abs))

    rel_path = _compute_relative(abs_path, base_path)
    if rel_path == ".":
        rel_path = ""

    if is_dir:
        source_for_copy = abs_path
        dest_path = f"{dest_root}/{rel_path}".rstrip("/")
    else:
        parent_dir = os.path.dirname(rel_path)
        source_for_copy = abs_path
        dest_path = f"{dest_root}/{parent_dir}".rstrip("/")

    copy_cmd = f'rclone copy --config ./rclone.conf "{source_for_copy}" "{dest_path}"'

    proc = await asyncio.create_subprocess_shell(
        copy_cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    _, err = await proc.communicate()
    if proc.returncode != 0:
        LOGGER.error(f"Rclone copy failed for '{source_for_copy}'.\nCMD: {copy_cmd}\nOutput:\n{err.decode().strip()}")
        return None, None, None

    rclone_link, index_link = None, None
    if bot_set.link_options in ['RCLONE', 'Both']:
        link_target = f"{dest_root}/{rel_path}".rstrip('/')
        link_cmd = f'rclone link --config ./rclone.conf "{link_target}"'
        t2 = await asyncio.create_subprocess_shell(
            link_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        so, _ = await t2.communicate()
        if t2.returncode == 0:
            rclone_link = so.decode().strip()

    if bot_set.link_options in ['Index', 'Both'] and Config.INDEX_LINK:
        index_link = f"{Config.INDEX_LINK}/{rel_path}".replace(' ', '%20')

    remote, base = '', ''
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
        'path': rel_path,
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
            # Handle the edge case where rel_path might be empty or just "."
            src_file = os.path.basename(rel_path) if rel_path else None

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


async def track_upload(metadata, user, base_path: str, index: int = None, total: int = None):
    if bot_set.upload_mode == 'Telegram':
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
        r_link, i_link, info = await _rclone_upload(user, metadata['filepath'], base_path)
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

    try:
        os.remove(metadata['filepath'])
        if metadata.get('thumbnail'):
            os.remove(metadata['thumbnail'])
    except Exception:
        pass


async def music_video_upload(metadata, user, base_path: str):
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
        r_link, i_link, info = await _rclone_upload(user, metadata['filepath'], base_path)
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

    try:
        os.remove(metadata['filepath'])
        if metadata.get('thumbnail'):
            os.remove(metadata['thumbnail'])
    except Exception:
        pass


async def album_upload(metadata, user, base_path: str):
    if bot_set.upload_mode == 'Telegram':
        if getattr(bot_set, 'tidal_ng_album_zip', False):
            zp = await create_tidal_ng_zip(metadata['folderpath'], user['user_id'], metadata)
            caption = await format_string(
                "💿 **{album}**\n👤 {artist}\n🎧 {provider}",
                {
                    'album': metadata['title'],
                    'artist': metadata['artist'],
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
            for idx, track in enumerate(tracks, start=1):
                await track_upload(track, user, base_path, index=idx, total=len(tracks))
    else:
        r_link, i_link, info = await _rclone_upload(user, metadata['folderpath'], base_path)
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

    shutil.rmtree(metadata['folderpath'])


async def playlist_upload(metadata, user, base_path: str):
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
            for idx, track in enumerate(tracks, start=1):
                await track_upload(track, user, base_path, index=idx, total=len(tracks))
    else:
        r_link, i_link, info = await _rclone_upload(user, metadata['folderpath'], base_path)
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

    shutil.rmtree(metadata['folderpath'])
