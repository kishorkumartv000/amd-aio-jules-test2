import os
import re
import asyncio
import logging
import shutil
from bot.helpers.utils import (
    run_apple_downloader,
    extract_title_from_url,
    extract_apple_music_id_and_type,
    fetch_apple_music_metadata_from_api,
    download_file,
    extract_apple_metadata,
    send_message,
    edit_message,
    format_string,
    cleanup,
    list_apple_output_files,
    cleanup_apple_global,
)
from bot.helpers.uploader import track_upload, album_upload, music_video_upload, artist_upload, playlist_upload
from bot.settings import bot_set
from bot.helpers.database.pg_impl import download_history
from config import Config
from bot.logger import LOGGER

logger = logging.getLogger(__name__)

class AppleMusicProvider:
    def __init__(self):
        self.name = "apple"
    
    def validate_url(self, url: str) -> bool:
        """Check if URL is valid Apple Music content"""
        return bool(re.match(
            r"https://music\.apple\.com/.+/(album|song|playlist|music-video)/.+", 
            url
        ))
    
    def extract_content_id(self, url: str) -> str:
        """Extract Apple Music content ID from URL"""
        match = re.search(r'/(album|song|playlist|music-video|artist)/[^/]+/(\d+)', url)
        return match.group(2) if match else "unknown"
    
    async def process(self, url: str, user: dict, options: dict = None) -> dict:
        """Process Apple Music URL with options"""
        # Create user-specific directory
        user_dir = os.path.join(Config.LOCAL_STORAGE, str(user['user_id']), "Apple Music")
        os.makedirs(user_dir, exist_ok=True)
        LOGGER.info(f"Created temporary working directory for Apple Music task: {user_dir}")
        
        # Process options
        cmd_options = self.build_options(options)

        # Initialize progress reporter
        from bot.helpers.progress import ProgressReporter

        # Try to get a title from the URL for early feedback
        url_title = extract_title_from_url(url)
        if url_title:
            label = f"Apple Music • {url_title}"
        else:
            label = f"Apple Music • ID: {user.get('task_id','?')}"

        reporter = ProgressReporter(user['bot_msg'], label=label, show_system_stats=False)
        user['progress'] = reporter
        await reporter.set_stage("Preparing")
        
        # Download content
        result = await run_apple_downloader(
            url,
            user_dir,
            cmd_options,
            user,
            progress=reporter,
            task_id=user.get('task_id'),
            cancel_event=user.get('cancel_event')
        )
        if not result['success']:
            LOGGER.error(f"Apple downloader failed: {result['error']}")
            return result
        
        # Find downloaded files from global Apple folders (alac/atmos/aac)
        files = list_apple_output_files()
        
        if not files:
            LOGGER.error("No files found in global Apple output folders")
            return {'success': False, 'error': "No files downloaded"}
        
        LOGGER.info(f"Found {len(files)} files in global Apple output folders")
        
        # Extract metadata
        items = []
        for file_path in files:
            try:
                metadata = await extract_apple_metadata(file_path)
                metadata['filepath'] = file_path
                metadata['provider'] = self.name
                items.append(metadata)
                LOGGER.info(f"Processed file: {file_path}")
            except Exception as e:
                LOGGER.error(f"Metadata extraction failed for {file_path}: {str(e)}")
        
        # Handle case where no metadata was extracted
        if not items:
            LOGGER.error("No valid metadata extracted for any files")
            return {'success': False, 'error': "Metadata extraction failed"}
        
        # Update progress with total tracks
        try:
            await user['progress'].set_total_tracks(len(items))
            await user['progress'].update_download(tracks_done=len(items))
        except Exception:
            pass
        
        # Determine content type based on file types
        has_video = any(f.endswith(('.mp4', '.m4v', '.mov')) for f in files)
        has_audio = any(f.endswith(('.m4a', '.flac', '.alac')) for f in files)
        is_single = len(items) == 1
        
        if is_single:
            if has_video:
                content_type = 'video'
                folder_path = os.path.dirname(items[0]['filepath'])
            else:
                content_type = 'track'
                folder_path = os.path.dirname(items[0]['filepath'])
        elif has_video and has_audio:
            # Mixed content - treat as playlist
            content_type = 'playlist'
            folder_path = os.path.dirname(os.path.commonpath([i['filepath'] for i in items]))
            LOGGER.warning(f"Mixed video/audio content detected. Treating as playlist: {folder_path}")
        else:
            # Pure audio collection
            content_type = 'album'
            folder_path = os.path.dirname(os.path.commonpath([i['filepath'] for i in items]))
        
        # Record download in history
        content_id = self.extract_content_id(url)
        quality = options.get('mv-max', Config.APPLE_ATMOS_QUALITY) if has_video else \
                 options.get('alac-max', Config.APPLE_ALAC_QUALITY) if 'alac' in (options or {}) else \
                 options.get('atmos-max', Config.APPLE_ATMOS_QUALITY)
        
        # Use first item's title if album title is missing
        album_title = items[0].get('album', items[0]['title'])
        
        download_history.record_download(
            user_id=user['user_id'],
            provider=self.name,
            content_type=content_type,
            content_id=content_id,
            title=album_title,
            artist=items[0]['artist'],
            quality=str(quality)  # Convert to string
        )
        
        # Use poster_msg from user dict if it exists, otherwise fall back to the bot_msg
        final_poster_msg = user.get('poster_msg', user['bot_msg'])
        return {
            'success': True,
            'type': content_type,
            'items': items,
            'folderpath': folder_path,
            'title': album_title,
            'artist': items[0]['artist'],
            'poster_msg': final_poster_msg
        }
    
    def build_options(self, options: dict) -> list:
        """Convert options dictionary to command-line flags"""
        if not options:
            return []
        
        cmd_options = []
        option_map = {
            'aac': '--aac',
            'aac-type': '--aac-type',
            'alac-max': '--alac-max',
            'all-album': '--all-album',
            'atmos': '--atmos',
            'atmos-max': '--atmos-max',
            'debug': '--debug',
            'mv-audio-type': '--mv-audio-type',
            'mv-max': '--mv-max',
            'select': '--select',
            'song': '--song'
        }
        
        for key, value in options.items():
            if key in option_map:
                if value is True:  # Flag option
                    cmd_options.append(option_map[key])
                else:  # Value option
                    cmd_options.extend([option_map[key], str(value)])
        
        return cmd_options

async def start_apple(link: str, user: dict, options: dict = None):
    """Handle Apple Music download request with options"""
    try:
        provider = AppleMusicProvider()
        if not provider.validate_url(link):
            await edit_message(user['bot_msg'], "❌ Invalid Apple Music URL")
            return

        # If rich metadata is enabled, try to fetch and post an art poster first
        if getattr(bot_set, 'apple_rich_metadata', False):
            content_id, content_type = extract_apple_music_id_and_type(link)
            if content_id and content_type == 'album':  # API is most reliable for albums
                api_meta = await fetch_apple_music_metadata_from_api(content_id, content_type)
                if api_meta and api_meta.get('cover_url'):
                    # Format the caption with details from the API
                    caption = f"💿 <b>{api_meta.get('title', 'Unknown Album')}</b>\n" \
                              f"👤 {api_meta.get('artist', 'Unknown Artist')}"
                    if api_meta.get('track_count'):
                        caption += f"\n🔢 {api_meta.get('track_count')} Tracks"
                    caption += f"\n🎧 {api_meta.get('provider', 'Apple Music')}"

                    # Send the poster message using the cover URL directly
                    poster_msg = await send_message(user, api_meta['cover_url'], 'pic', caption=caption)
                    if poster_msg:
                        # Store the poster message to be used by the progress reporter and uploader
                        user['poster_msg'] = poster_msg

        # Process content with options
        result = await provider.process(link, user, options)
        if not result['success']:
            await edit_message(user['bot_msg'], f"❌ Error: {result['error']}")
            # Also delete the poster if it was created
            if user.get('poster_msg') and user['poster_msg'] != user['bot_msg']:
                try:
                    await user['poster_msg'].delete()
                except Exception:
                    pass
            return
        
        # Process and upload content based on type
        if result['type'] == 'track':
            await track_upload(result['items'][0], user)
        elif result['type'] == 'video':
            # Update label to show video emoji
            try:
                if user.get('progress'):
                    user['progress'].label = f"🎬 Apple Music • ID: {user.get('task_id','?')}"
            except Exception:
                pass
            await music_video_upload(result['items'][0], user)
        elif result['type'] == 'album':
            await album_upload(result, user)
        elif result['type'] == 'playlist':
            await playlist_upload(result, user)
        else:
            await edit_message(user['bot_msg'], f"❌ Unsupported content type: {result['type']}")
            return
        
        # Final cleanup
        try:
            await user['progress'].set_stage("Finalizing")
        except Exception:
            pass
        await cleanup(user)
        # Clean only the contents of global Apple output folders
        cleanup_apple_global()
        try:
            await user['progress'].set_stage("Done")
        except Exception:
            await edit_message(user['bot_msg'], "✅ Apple Music download completed!")
        
    except asyncio.CancelledError:
        try:
            await edit_message(user['bot_msg'], "⏹️ Task cancelled. Cleaning up…")
        except Exception:
            pass
        await cleanup(user)
        raise
    except Exception as e:
        logger.error(f"Apple Music error: {str(e)}", exc_info=True)
        try:
            await user.get('progress', None).set_stage("Done")
        except Exception:
            await edit_message(user['bot_msg'], f"❌ Error: {str(e)}")
        await cleanup(user)
