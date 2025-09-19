import os
import shutil
import zipfile
import asyncio
from config import Config
from bot.helpers.utils import create_apple_zip, format_string, send_message, edit_message, zip_handler, MAX_SIZE
from bot.logger import LOGGER
from mutagen import File
from mutagen.mp4 import MP4
import re
from bot.settings import bot_set
from bot.helpers.progress import ProgressReporter
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

async def track_upload(metadata, user, index: int = None, total: int = None):
    """
    Upload a single track
    Args:
        metadata: Track metadata
        user: User details
        index: Optional file index for progress display
        total: Optional total files for progress display
    """
    # Determine base path for different providers
    if "Apple Music" in metadata['filepath']:
        base_path = os.path.join(Config.LOCAL_STORAGE, str(user['user_id']), "Apple Music")
    else:
        base_path = Config.LOCAL_STORAGE
    
    if bot_set.upload_mode == 'Telegram':
        reporter = user.get('progress')
        if reporter:
            await reporter.set_stage("Uploading")
        await send_message(
            user,
            metadata['filepath'],
            'audio',
            caption=await format_string(
                "🎵 **{title}**\n👤 {artist}\n🎧 {provider}",
                {
                    'title': metadata['title'],
                    'artist': metadata['artist'],
                    'provider': metadata.get('provider', 'Apple Music')
                }
            ),
            meta={
                'duration': metadata['duration'],
                'artist': metadata['artist'],
                'title': metadata['title'],
                'thumbnail': metadata['thumbnail']
            },
            progress_reporter=reporter,
            progress_label="Uploading",
            file_index=index,
            total_files=total,
            cancel_event=user.get('cancel_event')
        )
    elif bot_set.upload_mode == 'RCLONE':
        rclone_link, index_link, remote_info = await rclone_upload(user, metadata['filepath'], base_path)
        text = await format_string(
            "🎵 **{title}**\n👤 {artist}\n🎧 {provider}\n🔗 [Direct Link]({r_link})",
            {
                'title': metadata['title'],
                'artist': metadata['artist'],
                'provider': metadata.get('provider', 'Apple Music'),
                'r_link': rclone_link
            }
        )
        if index_link:
            text += f"\n📁 [Index Link]({index_link})"
        await send_message(user, text)
        await _post_rclone_manage_button(user, remote_info)
    
    # Cleanup
    try:
        await asyncio.to_thread(os.remove, metadata['filepath'])
        if metadata.get('thumbnail'):
            await asyncio.to_thread(os.remove, metadata['thumbnail'])
    except Exception as e:
        LOGGER.error(f"Error during file cleanup for track {metadata.get('title')}: {e}")

async def music_video_upload(metadata, user):
    """
    Upload a music video
    Args:
        metadata: Video metadata
        user: User details
    """
    # Determine base path for different providers
    if "Apple Music" in metadata['filepath']:
        base_path = os.path.join(Config.LOCAL_STORAGE, str(user['user_id']), "Apple Music")
    else:
        base_path = Config.LOCAL_STORAGE
    
    if bot_set.upload_mode == 'Telegram':
        reporter = user.get('progress')
        if reporter:
            await reporter.set_stage("Uploading")
        # Decide media type based on setting
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
                    'provider': metadata.get('provider', 'Apple Music')
                }
            ),
            meta=metadata,  # PASS METADATA HERE
            progress_reporter=reporter,
            progress_label="Uploading",
            file_index=1,
            total_files=1,
            cancel_event=user.get('cancel_event')
        )
    elif bot_set.upload_mode == 'RCLONE':
        rclone_link, index_link, remote_info = await rclone_upload(user, metadata['filepath'], base_path)
        text = await format_string(
            "🎬 **{title}**\n👤 {artist}\n🎧 {provider} Music Video\n🔗 [Direct Link]({r_link})",
            {
                'title': metadata['title'],
                'artist': metadata['artist'],
                'provider': metadata.get('provider', 'Apple Music'),
                'r_link': rclone_link
            }
        )
        if index_link:
            text += f"\n📁 [Index Link]({index_link})"
        await send_message(user, text)
        await _post_rclone_manage_button(user, remote_info)
    
    # Cleanup
    try:
        await asyncio.to_thread(os.remove, metadata['filepath'])
        if metadata.get('thumbnail'):
            await asyncio.to_thread(os.remove, metadata['thumbnail'])
    except Exception as e:
        LOGGER.error(f"Error during file cleanup for music video {metadata.get('title')}: {e}")

async def _get_folder_size(folder_path: str) -> int:
    total_size = 0
    # os.walk is synchronous, but the I/O bound part is getsize.
    # We can collect all file paths first and then get sizes concurrently.
    # However, for simplicity and to avoid holding many paths in memory,
    # we will make each getsize call non-blocking sequentially.
    for root, _, files in os.walk(folder_path):
        for f in files:
            try:
                file_path = os.path.join(root, f)
                total_size += await asyncio.to_thread(os.path.getsize, file_path)
            except Exception:
                continue
    return total_size


async def album_upload(metadata, user):
    """
    Upload an album
    Args:
        metadata: Album metadata
        user: User details
    """
    # Determine base path for different providers
    if "Apple Music" in metadata['folderpath']:
        base_path = os.path.join(Config.LOCAL_STORAGE, str(user['user_id']), "Apple Music")
    else:
        base_path = Config.LOCAL_STORAGE
    
    if bot_set.upload_mode == 'Telegram':
        reporter = user.get('progress')
        # Use Apple-specific toggle; do not rely on core
        use_zip = bool(getattr(bot_set, 'apple_album_zip', False))
        if use_zip:
            # Decide zipping strategy based on folder size and Telegram limits
            total_size = await _get_folder_size(metadata['folderpath'])
            zip_paths = []
            if total_size > MAX_SIZE:
                # Split into multiple zips for Telegram
                z = await zip_handler(metadata['folderpath'])
                zip_paths = z if isinstance(z, list) else [z]
            else:
                # Single descriptive zip with progress
                zip_path = await create_apple_zip(
                    metadata['folderpath'], 
                    user['user_id'],
                    metadata,
                    progress=reporter,
                    cancel_event=user.get('cancel_event')
                )
                zip_paths = [zip_path]
            
            # Create caption with provider info
            caption = await format_string(
                "💿 **{album}**\n👤 {artist}\n🎧 {provider}",
                {
                    'album': metadata['title'],
                    'artist': metadata['artist'],
                    'provider': metadata.get('provider', 'Apple Music')
                }
            )
            
            total_parts = len(zip_paths)
            for idx, zp in enumerate(zip_paths, start=1):
                await send_message(
                    user,
                    zp,
                    'doc',
                    caption=caption,
                    progress_reporter=reporter,
                    progress_label="Uploading",
                    file_index=idx,
                    total_files=total_parts
                )
                # Clean up zip file after upload
                try:
                    await asyncio.to_thread(os.remove, zp)
                except Exception as e:
                    LOGGER.error(f"Error during zip cleanup for album {metadata.get('title')}: {e}")
        else:
            # Upload tracks individually
            tracks = metadata.get('tracks') or metadata.get('items', [])
            total_tracks = len(tracks)
            for idx, track in enumerate(tracks, start=1):
                await track_upload(track, user, index=idx, total=total_tracks)
    elif bot_set.upload_mode == 'RCLONE':
        rclone_link, index_link, remote_info = await rclone_upload(user, metadata['folderpath'], base_path)
        text = await format_string(
            "💿 **{album}**\n👤 {artist}\n🎧 {provider}\n🔗 [Direct Link]({r_link})",
            {
                'album': metadata['title'],
                'artist': metadata['artist'],
                'provider': metadata.get('provider', 'Apple Music'),
                'r_link': rclone_link
            }
        )
        if index_link:
            text += f"\n📁 [Index Link]({index_link})"
        
        if metadata.get('poster_msg'):
            await edit_message(metadata['poster_msg'], text)
        else:
            await send_message(user, text)
        await _post_rclone_manage_button(user, remote_info)
    
    # Cleanup
    shutil.rmtree(metadata['folderpath'])

async def artist_upload(metadata, user):
    """
    Upload an artist's content
    Args:
        metadata: Artist metadata
        user: User details
    """
    # Determine base path for different providers
    if "Apple Music" in metadata['folderpath']:
        base_path = os.path.join(Config.LOCAL_STORAGE, str(user['user_id']), "Apple Music")
    else:
        base_path = Config.LOCAL_STORAGE
    
    if bot_set.upload_mode == 'Telegram':
        reporter = user.get('progress')
        if bot_set.artist_zip:
            # Decide zipping strategy based on size
            total_size = await _get_folder_size(metadata['folderpath'])
            zip_paths = []
            if total_size > MAX_SIZE:
                z = await zip_handler(metadata['folderpath'])
                zip_paths = z if isinstance(z, list) else [z]
            else:
                zip_path = await create_apple_zip(
                    metadata['folderpath'], 
                    user['user_id'],
                    metadata,
                    progress=reporter,
                    cancel_event=user.get('cancel_event')
                )
                zip_paths = [zip_path]
            
            # Create caption with provider info
            caption = await format_string(
                "🎤 **{artist}**\n🎧 {provider} Discography",
                {
                    'artist': metadata['title'],
                    'provider': metadata.get('provider', 'Apple Music')
                }
            )
            
            total_parts = len(zip_paths)
            for idx, zp in enumerate(zip_paths, start=1):
                await send_message(
                    user,
                    zp,
                    'doc',
                    caption=caption,
                    progress_reporter=reporter,
                    progress_label="Uploading",
                    file_index=idx,
                    total_files=total_parts
                )
                try:
                    await asyncio.to_thread(os.remove, zp)
                except Exception as e:
                    LOGGER.error(f"Error during zip cleanup for artist {metadata.get('title')}: {e}")
        else:
            # Upload albums or tracks individually
            if 'albums' in metadata:
                for album in metadata['albums']:
                    await album_upload(album, user)
            else:
                tracks = metadata.get('tracks') or metadata.get('items', [])
                total_tracks = len(tracks)
                for idx, track in enumerate(tracks, start=1):
                    await track_upload(track, user, index=idx, total=total_tracks)
    elif bot_set.upload_mode == 'RCLONE':
        rclone_link, index_link, remote_info = await rclone_upload(user, metadata['folderpath'], base_path)
        text = await format_string(
            "🎤 **{artist}**\n🎧 {provider} Discography\n🔗 [Direct Link]({r_link})",
            {
                'artist': metadata['title'],
                'provider': metadata.get('provider', 'Apple Music'),
                'r_link': rclone_link
            }
        )
        if index_link:
            text += f"\n📁 [Index Link]({index_link})"
        await send_message(user, text)
        await _post_rclone_manage_button(user, remote_info)
    
    # Cleanup
    shutil.rmtree(metadata['folderpath'])

async def playlist_upload(metadata, user):
    """
    Upload a playlist
    Args:
        metadata: Playlist metadata
        user: User details
    """
    # Determine base path for different providers
    if "Apple Music" in metadata['folderpath']:
        base_path = os.path.join(Config.LOCAL_STORAGE, str(user['user_id']), "Apple Music")
    else:
        base_path = Config.LOCAL_STORAGE
    
    if bot_set.upload_mode == 'Telegram':
        reporter = user.get('progress')
        # Use Apple-specific toggle; do not rely on core
        use_zip = bool(getattr(bot_set, 'apple_playlist_zip', False))
        if use_zip:
            # Decide zipping strategy based on size
            total_size = await _get_folder_size(metadata['folderpath'])
            zip_paths = []
            if total_size > MAX_SIZE:
                z = await zip_handler(metadata['folderpath'])
                zip_paths = z if isinstance(z, list) else [z]
            else:
                # Create descriptive zip file
                zip_path = await create_apple_zip(
                    metadata['folderpath'], 
                    user['user_id'],
                    metadata,
                    progress=reporter,
                    cancel_event=user.get('cancel_event')
                )
                zip_paths = [zip_path]
            
            # Create caption with provider info
            caption = await format_string(
                "🎵 **{title}**\n👤 Curated by {artist}\n🎧 {provider} Playlist",
                {
                    'title': metadata['title'],
                    'artist': metadata.get('artist', 'Various Artists'),
                    'provider': metadata.get('provider', 'Apple Music')
                }
            )
            
            total_parts = len(zip_paths)
            for idx, zp in enumerate(zip_paths, start=1):
                await send_message(
                    user,
                    zp,
                    'doc',
                    caption=caption,
                    progress_reporter=reporter,
                    progress_label="Uploading",
                    file_index=idx,
                    total_files=total_parts
                )
                try:
                    await asyncio.to_thread(os.remove, zp)
                except Exception as e:
                    LOGGER.error(f"Error during zip cleanup for playlist {metadata.get('title')}: {e}")
        else:
            # Upload tracks individually
            tracks = metadata.get('tracks') or metadata.get('items', [])
            total_tracks = len(tracks)
            for idx, track in enumerate(tracks, start=1):
                await track_upload(track, user, index=idx, total=total_tracks)
    elif bot_set.upload_mode == 'RCLONE':
        rclone_link, index_link, remote_info = await rclone_upload(user, metadata['folderpath'], base_path)
        text = await format_string(
            "🎵 **{title}**\n👤 Curated by {artist}\n🎧 {provider} Playlist\n🔗 [Direct Link]({r_link})",
            {
                'title': metadata['title'],
                'artist': metadata.get('artist', 'Various Artists'),
                'provider': metadata.get('provider', 'Apple Music'),
                'r_link': rclone_link
            }
        )
        if index_link:
            text += f"\n📁 [Index Link]({index_link})"
        await send_message(user, text)
        await _post_rclone_manage_button(user, remote_info)
    
    # Cleanup
    shutil.rmtree(metadata['folderpath'])

async def rclone_upload(user, path, base_path):
    """
    Upload files via Rclone
    Args:
        user: User details
        path: File or folder path
        base_path: Base path used to compute relative path for remote
    """
    # Ensure destination is configured
    dest_root = (getattr(bot_set, 'rclone_dest', None) or Config.RCLONE_DEST)
    if not dest_root:
        return None, None, None

    # Normalize source path
    abs_path = os.path.abspath(path)

    # Compute relative path under a sensible root so remote path matches layout
    def _compute_relative(p: str, base: str | None) -> str:
        try:
            p_abs = os.path.abspath(p)
            if base:
                base_abs = os.path.abspath(base)
                if p_abs.startswith(base_abs):
                    return os.path.normpath(os.path.relpath(p_abs, base_abs))
        except Exception:
            pass
        # Fallback: try to anchor at "Apple Music" if present
        if "Apple Music" in abs_path:
            try:
                parts = p_abs.split(os.sep)
                if "Apple Music" in parts:
                    idx = parts.index("Apple Music")
                    root = os.sep.join(parts[:idx + 1])
                    return os.path.normpath(os.path.relpath(p_abs, root))
            except Exception:
                pass
        # Last resort: basename
        return os.path.basename(p_abs) if os.path.isfile(p_abs) else os.path.basename(os.path.normpath(p_abs))

    # Decide scope: FILE (existing) vs FOLDER (full folder tree)
    scope = getattr(bot_set, 'rclone_copy_scope', 'FILE').upper()
    is_directory = os.path.isdir(abs_path)

    if scope == 'FOLDER':
        # Resolve the root folder we should copy
        if is_directory:
            source_for_copy = abs_path
            relative_path = _compute_relative(abs_path, base_path)
            dest_path = f"{dest_root}/{relative_path}".rstrip("/")
        else:
            # Copy the parent folder that contains the file
            parent_dir_abs = os.path.dirname(abs_path)
            source_for_copy = parent_dir_abs
            relative_path = _compute_relative(parent_dir_abs, base_path)
            dest_path = f"{dest_root}/{relative_path}".rstrip("/")
            is_directory = True
    else:
        # FILE scope: keep existing behavior
        relative_path = _compute_relative(abs_path, base_path)
        if is_directory:
            source_for_copy = abs_path
            dest_path = f"{dest_root}/{relative_path}".rstrip("/")
        else:
            parent_dir = os.path.dirname(relative_path)
            source_for_copy = abs_path
            dest_path = f"{dest_root}/{parent_dir}".rstrip("/")

    # 1) Copy source to remote destination
    copy_cmd = f'rclone copy --config ./rclone.conf "{source_for_copy}" "{dest_path}"'
    copy_task = await asyncio.create_subprocess_shell(
        copy_cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    copy_stdout, copy_stderr = await copy_task.communicate()
    if copy_task.returncode != 0:
        try:
            LOGGER.debug(f"Rclone copy failed: {copy_stderr.decode().strip()}")
        except Exception:
            pass
        # Even if copy fails, return None links so caller can handle gracefully
        return None, None, None

    # 2) Build links
    rclone_link = None
    index_link = None

    # Rclone share link
    if bot_set.link_options in ['RCLONE', 'Both']:
        # Link target should reflect the relative root of the uploaded entity
        link_target = f"{dest_root}/{relative_path}".rstrip("/")
        link_cmd = f'rclone link --config ./rclone.conf "{link_target}"'
        link_task = await asyncio.create_subprocess_shell(
            link_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await link_task.communicate()
        if link_task.returncode == 0:
            try:
                rclone_link = stdout.decode().strip()
            except Exception:
                rclone_link = None
        else:
            try:
                LOGGER.debug(f"Failed to get Rclone link: {stderr.decode().strip()}")
            except Exception:
                pass

    # Optional index link
    if bot_set.link_options in ['Index', 'Both'] and Config.INDEX_LINK:
        # Do not URL-encode here to keep behavior in line with current uploader; indexers usually handle spaces
        index_link = f"{Config.INDEX_LINK}/{relative_path}".replace(" ", "%20")

    # Remote info for post-upload manage flow
    # Parse remote name and base path from dest_root (format remote:base)
    remote_name = ''
    remote_base = ''
    try:
        if dest_root and ':' in dest_root:
            remote_name, remote_base = dest_root.split(':', 1)
            remote_base = remote_base.strip('/')
        else:
            remote_name = (getattr(bot_set, 'rclone_remote', '') or dest_root or '').rstrip(':')
            remote_base = ''
    except Exception:
        remote_name = (getattr(bot_set, 'rclone_remote', '') or (Config.RCLONE_DEST.split(':',1)[0] if Config.RCLONE_DEST and ':' in Config.RCLONE_DEST else '')).rstrip(':')
        remote_base = ''

    remote_info = {
        'remote': remote_name,
        'base': remote_base,
        'path': relative_path,
        'is_dir': is_directory
    }

    return rclone_link, index_link, remote_info

async def _post_rclone_manage_button(user, remote_info: dict):
    try:
        from ..helpers.database.pg_impl import rclone_sessions_db
        import uuid

        # Generate a unique token for the session
        token = uuid.uuid4().hex[:10]

        # Prepare the context to be stored in the database
        src_remote = remote_info.get('remote')
        rel_path = remote_info.get('path') or ''
        is_dir = bool(remote_info.get('is_dir'))

        if is_dir:
            src_path = rel_path
            src_file = None
        else:
            src_path = os.path.dirname(rel_path)
            src_file = rel_path

        context = {
            'src_remote': src_remote,
            'base': remote_info.get('base') if isinstance(remote_info, dict) else None,
            'src_path': src_path,
            'src_file': src_file,
            'dst_remote': None,
            'dst_path': '',
            'cc_mode': 'copy',
            'src_page': 0
        }

        # Save the session to the database
        rclone_sessions_db.add_session(
            token=token,
            user_id=user['user_id'],
            context=context
        )

        # Button to open manage UI, with the token in the callback
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📂 Browse uploaded (Copy/Move)", callback_data=f"rcloneManageStart|{token}")]
        ])
        await send_message(user, "Manage the uploaded item:", markup=kb)
    except Exception as e:
        try:
            LOGGER.error(f"Failed to create rclone manage button: {e}", exc_info=True)
            await send_message(user, "Note: manage button unavailable.")
        except Exception:
            pass
