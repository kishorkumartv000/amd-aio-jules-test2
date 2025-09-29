import os
import math
import aiohttp
import asyncio
import shutil
import zipfile
import re
import subprocess
import json
import base64
import time
import mutagen
from mutagen.mp4 import MP4
from pathlib import Path
from urllib.parse import quote
from aiohttp import ClientTimeout
from concurrent.futures import ThreadPoolExecutor
from pyrogram.errors import FloodWait
from typing import Optional
from .progress import ProgressReporter

# Import Config for Apple Music settings
from config import Config
import bot.helpers.translations as lang

from ..logger import LOGGER
from ..settings import bot_set
from .buttons.links import links_button
from .message import send_message, edit_message

MAX_SIZE = 1.9 * 1024 * 1024 * 1024  # 2GB

async def download_file(url, path, retries=3, timeout=30, cancel_event: asyncio.Event | None = None):
    """
    Download a file with retry logic, timeout, and cooperative cancellation
    Args:
        url (str): URL to download
        path (str): Full path to save the file
        retries (int): Number of retry attempts
        timeout (int): Timeout in seconds
        cancel_event: Optional asyncio.Event to signal cancellation
    Returns:
        str or None: Error message if failed, else None
    """
    os.makedirs(os.path.dirname(path), exist_ok=True)
    
    for attempt in range(1, retries + 1):
        try:
            if cancel_event and cancel_event.is_set():
                # Clean partial file if any
                try:
                    if os.path.exists(path):
                        os.remove(path)
                except Exception:
                    pass
                return "Cancelled"
            async with aiohttp.ClientSession(timeout=ClientTimeout(total=timeout)) as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        with open(path, 'wb') as f:
                            async for chunk in response.content.iter_chunked(1024 * 4):
                                if cancel_event and cancel_event.is_set():
                                    try:
                                        f.close()
                                    except Exception:
                                        pass
                                    try:
                                        if os.path.exists(path):
                                            os.remove(path)
                                    except Exception:
                                        pass
                                    return "Cancelled"
                                f.write(chunk)
                        return None
                    else:
                        return f"HTTP Status: {response.status}"
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            if attempt == retries:
                return f"Failed after {retries} attempts: {str(e)}"
            await asyncio.sleep(2 ** attempt)
        except Exception as e:
            return f"Unexpected error: {str(e)}"


async def format_string(text:str, data:dict, user=None):
    """
    Format text using metadata placeholders
    Args:
        text: Template text with placeholders
        data: Metadata dictionary
        user: User details
    Returns:
        Formatted string
    """
    replacements = {
        '{title}': data.get('title', ''),
        '{album}': data.get('album', ''),
        '{artist}': data.get('artist', ''),
        '{albumartist}': data.get('albumartist', ''),
        '{tracknumber}': str(data.get('tracknumber', '')),
        '{date}': str(data.get('date', '')),
        '{upc}': str(data.get('upc', '')),
        '{isrc}': str(data.get('isrc', '')),
        '{totaltracks}': str(data.get('totaltracks', '')),
        '{volume}': str(data.get('volume', '')),
        '{totalvolume}': str(data.get('totalvolume', '')),
        '{extension}': data.get('extension', ''),
        '{duration}': str(data.get('duration', '')),
        '{copyright}': data.get('copyright', ''),
        '{genre}': data.get('genre', ''),
        '{provider}': data.get('provider', '').title(),
        '{quality}': data.get('quality', ''),
        '{explicit}': str(data.get('explicit', '')),
    }
    
    if user:
        replacements['{user}'] = user.get('name', '')
        replacements['{username}'] = user.get('user_name', '')
    
    for key, value in replacements.items():
        text = text.replace(key, value)
        
    return text


async def run_concurrent_tasks(tasks, progress_details=None):
    """
    Run tasks concurrently with progress tracking
    Args:
        tasks: List of async tasks
        progress_details: Progress message details
    Returns:
        Results of all tasks
    """
    semaphore = asyncio.Semaphore(Config.MAX_WORKERS)
    completed = 0
    total = len(tasks)
    
    async def run_task(task):
        nonlocal completed
        async with semaphore:
            result = await task
            completed += 1
            if progress_details:
                progress = int((completed / total) * 100)
                try:
                    await edit_message(
                        progress_details['msg'],
                        f"{progress_details['text']}\nProgress: {progress}%"
                    )
                except FloodWait:
                    pass
            return result
            
    return await asyncio.gather(*(run_task(task) for task in tasks))


async def create_link(path, basepath):
    """
    Create rclone and index links
    Args:
        path: Full file path
        basepath: Base directory path
    Returns:
        rclone_link, index_link
    """
    # Normalize inputs; fall back to basename if relative fails
    try:
        path = str(Path(path).resolve().relative_to(Path(basepath).resolve()))
    except Exception:
        try:
            path = os.path.basename(path) if os.path.isfile(path) else os.path.basename(os.path.normpath(path))
        except Exception:
            path = os.path.basename(str(path))

    rclone_link = None
    index_link = None

    if bot_set.link_options in ['RCLONE', 'Both']:
        cmd = f'rclone link --config ./rclone.conf "{Config.RCLONE_DEST}/{path}"'
        task = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await task.communicate()

        if task.returncode == 0:
            rclone_link = stdout.decode().strip()
        else:
            error_message = stderr.decode().strip()
            LOGGER.debug(f"Failed to get link: {error_message}")
            
    if bot_set.link_options in ['Index', 'Both']:
        if Config.INDEX_LINK:
            index_link =  Config.INDEX_LINK + '/' + quote(path)

    return rclone_link, index_link


async def zip_handler(folderpath):
    """
    Zip folder based on upload mode
    Args:
        folderpath: Path to folder
    Returns:
        List of zip paths
    """
    loop = asyncio.get_running_loop()
    with ThreadPoolExecutor() as pool:
        if bot_set.upload_mode == 'Telegram':
            zips = await loop.run_in_executor(pool, split_zip_folder, folderpath)
        else:
            zips = await loop.run_in_executor(pool, zip_folder, folderpath)
        return zips


def split_zip_folder(folderpath) -> list:
    """
    Split large folders into multiple zip files
    Args:
        folderpath: Path to folder
    Returns:
        List of zip file paths
    """
    zip_paths = []
    part_num = 1
    current_size = 0
    current_files = []

    def add_to_zip(zip_name, files_to_add):
        nonlocal part_num
        if part_num == 1:
            zip_path = f"{zip_name}.zip"
        else:
            zip_path = f"{zip_name}.part{part_num}.zip"

        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for file_path, arcname in files_to_add:
                zipf.write(file_path, arcname)
                os.remove(file_path)  # Delete after zipping
        return zip_path

    for root, dirs, files in os.walk(folderpath):
        for file in files:
            file_path = os.path.join(root, file)
            file_size = os.path.getsize(file_path)
            arcname = os.path.relpath(file_path, folderpath)

            # Start new zip if adding would exceed max size
            if current_size + file_size > MAX_SIZE:
                zip_paths.append(add_to_zip(folderpath, current_files))
                part_num += 1
                current_files = []
                current_size = 0

            # Add to current group
            current_files.append((file_path, arcname))
            current_size += file_size

    # Create final zip with remaining files
    if current_files:
        zip_paths.append(add_to_zip(folderpath, current_files))

    return zip_paths


def zip_folder(folderpath) -> str:
    """
    Create single zip of folder
    Args:
        folderpath: Path to folder
    Returns:
        Path to zip file
    """
    zip_path = f"{folderpath}.zip"
    
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(folderpath):
            for file in files:
                file_path = os.path.join(root, file)
                zipf.write(file_path, os.path.relpath(file_path, folderpath))
                os.remove(file_path)
    
    return zip_path


async def move_sorted_playlist(metadata, user) -> str:
    """
    Organize playlist files into folder structure
    Args:
        metadata: Playlist metadata
        user: User details
    Returns:
        Path to playlist folder
    """
    source_folder = f"{Config.DOWNLOAD_BASE_DIR}/{user['r_id']}/{metadata['provider']}"
    destination_folder = f"{Config.DOWNLOAD_BASE_DIR}/{user['r_id']}/{metadata['provider']}/{metadata['title']}"

    os.makedirs(destination_folder, exist_ok=True)

    # Move all artist/album folders
    folders = [
        os.path.join(source_folder, name) for name in os.listdir(source_folder) 
        if os.path.isdir(os.path.join(source_folder, name))
    ]

    for folder in folders:
        shutil.move(folder, destination_folder)

    return destination_folder


async def post_art_poster(user:dict, meta:dict):
    """
    Post album/playlist art as image
    Args:
        user: User details
        meta: Item metadata
    Returns:
        Message object
    """
    photo = meta['cover']
    if meta['type'] == 'album':
        caption = await format_string(lang.s.ALBUM_TEMPLATE, meta, user)
    else:
        caption = await format_string(lang.s.PLAYLIST_TEMPLATE, meta, user)
    
    if bot_set.art_poster:
        return await send_message(user, photo, 'pic', caption)


async def create_simple_text(meta, user):
    """
    Create simple caption for items
    Args:
        meta: Item metadata
        user: User details
    Returns:
        Formatted caption text
    """
    return await format_string(
        lang.s.SIMPLE_TITLE.format(
            meta['title'],
            meta['type'].title(),
            meta['provider']
        ), 
        meta, 
        user
    )


async def edit_art_poster(metadata, user, r_link, i_link, caption):
    """
    Edit existing art poster with links
    Args:
        metadata: Item metadata
        user: User details
        r_link: Rclone link
        i_link: Index link
        caption: Text to display
    """
    markup = links_button(r_link, i_link)
    await edit_message(
        metadata['poster_msg'],
        caption,
        markup
    )


async def post_simple_message(user, meta, r_link=None, i_link=None):
    """
    Send simple message with optional links
    Args:
        user: User details
        meta: Item metadata
        r_link: Rclone link
        i_link: Index link
    Returns:
        Message object
    """
    caption = await create_simple_text(meta, user)
    markup = links_button(r_link, i_link)
    return await send_message(user, caption, markup=markup)


async def progress_message(done, total, details):
    """
    Update progress message
    Args:
        done: Completed items
        total: Total items
        details: Progress message details
    """
    filled = math.floor((done / total) * 10)
    empty = 10 - filled
    
    progress_bar = "{0}{1}".format(
        ''.join(["▰" for _ in range(filled)]),
        ''.join(["▱" for _ in range(empty)])
    )

    try:
        await edit_message(
            details['msg'],
            details['text'].format(
                progress_bar, 
                done, 
                total, 
                details['title'],
                details['type'].title()
            ),
            None,
            False
        )
    except FloodWait:
        pass  # Skip update during flood limits


async def cleanup(user=None, metadata=None):
    """
    Clean up downloaded files
    Args:
        user: User details (cleans user directory)
        metadata: Item metadata (cleans specific item)
    """
    if metadata:
        try:
            # Apple Music specific cleanup
            if "Apple Music" in metadata.get('folderpath', ''):
                if os.path.exists(metadata['folderpath']):
                    shutil.rmtree(metadata['folderpath'], ignore_errors=True)
                return
            
            # Existing cleanup for other providers
            if metadata['type'] == 'album':
                is_zip = bot_set.album_zip
            elif metadata['type'] == 'artist':
                is_zip = bot_set.artist_zip
            else:
                is_zip = bot_set.playlist_zip
                
            if is_zip:
                paths = metadata['folderpath'] if isinstance(metadata['folderpath'], list) else [metadata['folderpath']]
                for path in paths:
                    try:
                        if os.path.exists(path):
                            os.remove(path)
                    except:
                        pass
            else:
                if os.path.exists(metadata['folderpath']):
                    shutil.rmtree(metadata['folderpath'], ignore_errors=True)
        except Exception as e:
            LOGGER.info(f"Metadata cleanup error: {str(e)}")
    
    if user:
        try:
            # Clean up Apple Music directory
            apple_dir = os.path.join(Config.LOCAL_STORAGE, str(user['user_id']), "Apple Music")
            if os.path.exists(apple_dir):
                shutil.rmtree(apple_dir, ignore_errors=True)
                # Remove parent user directory if now empty
                user_dir = os.path.join(Config.LOCAL_STORAGE, str(user['user_id']))
                try:
                    if os.path.isdir(user_dir) and not os.listdir(user_dir):
                        os.rmdir(user_dir)
                except Exception:
                    pass
        except Exception as e:
            LOGGER.info(f"Apple cleanup error: {str(e)}")
        
        try:
            # Clean up old-style directories
            old_dir = f"{Config.DOWNLOAD_BASE_DIR}/{user['r_id']}/"
            if os.path.exists(old_dir):
                shutil.rmtree(old_dir, ignore_errors=True)
        except Exception as e:
            LOGGER.info(f"Old dir cleanup error: {str(e)}")
        
        try:
            temp_dir = f"{Config.DOWNLOAD_BASE_DIR}/{user['r_id']}-temp/"
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception as e:
            LOGGER.info(f"Temp dir cleanup error: {str(e)}")

# Apple Music specific utilities

def extract_title_from_url(url: str) -> str | None:
    """
    Extracts a display-friendly title from an Apple Music URL slug.
    Example: https://music.apple.com/us/album/the-dark-side-of-the-moon/401291891
    Returns: "The Dark Side Of The Moon"
    """
    match = re.search(r"music\.apple\.com/[^/]+/(album|playlist)/([^/]+)/", url)
    if match:
        # Slug is like "the-dark-side-of-the-moon"
        slug = match.group(2)
        # Replace hyphens and capitalize words
        title = ' '.join(word.capitalize() for word in slug.split('-'))
        return title
    return None


async def run_apple_downloader(url: str, output_dir: str, options: list = None, user: dict = None, progress=None, task_id: str | None = None, cancel_event: asyncio.Event | None = None) -> dict:
    """
    Execute Apple Music downloader script with real-time progress.

    Args:
        url: Apple Music URL to download
        output_dir: Unused for Apple (kept for interface compatibility)
        options: List of command-line options
        user: User details for progress updates
        progress: Optional ProgressReporter for rich progress updates
        task_id: Optional task id to register subprocess for cancellation
        cancel_event: Optional cancellation event to cooperatively stop

    Returns:
        dict: {'success': bool, 'error': str if failed}
    """
    # Build command with options
    cmd = [Config.DOWNLOADER_PATH]
    if options:
        cmd.extend(options)
    cmd.append(url)

    LOGGER.info(f"Running Apple downloader: {' '.join(cmd)}")

    # Set a large buffer limit for readline to handle long lines without newlines
    limit = 1024 * 1024  # 1 MB

    # Run the command
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        limit=limit
    )

    # Register subprocess for external cancellation
    try:
        if task_id:
            from bot.helpers.tasks import task_manager
            await task_manager.register_subprocess(task_id, process)
    except Exception:
        pass

    # Process stdout line-by-line for real-time progress
    stdout_lines = []
    stage_set = False
    while True:
        # Check for cancellation first
        if cancel_event and cancel_event.is_set():
            try:
                process.terminate()
                await asyncio.wait_for(process.wait(), timeout=5)
            except Exception:
                process.kill()
            return {'success': False, 'error': 'Cancelled'}

        # Break loop if stdout is closed
        if process.stdout.at_eof():
            break

        try:
            line_bytes = await process.stdout.readline()
            if not line_bytes:
                break

            line_str = line_bytes.decode(errors='ignore').strip()
            stdout_lines.append(line_str)
            LOGGER.debug(f"Apple Downloader: {line_str}")

            # Update progress based on the current line (simplified to per-track)
            if progress:
                try:
                    # Look for X/Y total pattern (e.g., "1/10" or "Downloading 1/10")
                    xy_match = re.search(r"(\d+)\s*/\s*(\d+)", line_str)
                    if xy_match:
                        done = int(xy_match.group(1))
                        total = int(xy_match.group(2))

                        if not stage_set:
                            await progress.set_stage("Downloading")
                            await progress.set_total_tracks(total)
                            stage_set = True

                        # Update progress based on number of tracks done
                        await progress.update_download(tracks_done=done)

                except Exception:
                    pass # Ignore parsing errors
            elif user and 'bot_msg' in user:
                # Fallback for simple message update if progress reporter is not used
                xy_match = re.search(r"(\d+)\s*/\s*(\d+)", line_str)
                if xy_match:
                    try:
                        done = int(xy_match.group(1))
                        total = int(xy_match.group(2))
                        await edit_message(user['bot_msg'], f"Apple Music Download: {done}/{total}")
                    except Exception:
                        pass
        except asyncio.CancelledError:
            raise # Propagate cancellation
        except Exception as e:
            LOGGER.error(f"Error reading stdout line from downloader: {e}")
            break # Exit loop on read error

    # Wait for process to finish and get final exit code and stderr
    await process.wait()
    stderr_bytes = await process.stderr.read()
    stderr = stderr_bytes.decode().strip()

    # Clear subprocess registration
    try:
        if task_id:
            from bot.helpers.tasks import task_manager
            await task_manager.clear_subprocess(task_id)
    except Exception:
        pass

    # Move to processing stage in UI
    try:
        if progress:
            await progress.set_stage("Processing")
    except Exception:
        pass

    # Check return code
    if process.returncode != 0:
        error_details = stderr or "\n".join(stdout_lines)
        LOGGER.error(f"Apple downloader failed with code {process.returncode}: {error_details}")
        return {'success': False, 'error': error_details}

    return {'success': True}


async def extract_audio_metadata(file_path: str) -> dict:
    """Extract metadata from audio files"""
    try:
        if file_path.endswith('.m4a'):
            audio = MP4(file_path)
            return {
                'title': audio.get('\xa9nam', ['Unknown'])[0],
                'artist': audio.get('\xa9ART', ['Unknown Artist'])[0],
                'album': audio.get('\xa9alb', ['Unknown Album'])[0],
                'duration': int(audio.info.length) if hasattr(audio, "info") else 0,
                'thumbnail': extract_cover_art(audio, file_path) if getattr(bot_set, 'extract_embedded_cover', True) else None
            }
        else:
            audio = mutagen.File(file_path)
            if not audio:
                return default_metadata(file_path)
            return {
                'title': audio.tags.get('title', ['Unknown'])[0] if hasattr(audio, "tags") else os.path.basename(file_path),
                'artist': audio.tags.get('artist', ['Unknown Artist'])[0] if hasattr(audio, "tags") else "Unknown Artist",
                'album': audio.tags.get('album', ['Unknown Album'])[0] if hasattr(audio, "tags") else "Unknown Album",
                'duration': int(audio.info.length) if hasattr(audio, "info") else 0,
                'thumbnail': (extract_cover_art(audio, file_path) if hasattr(audio, 'pictures') and getattr(bot_set, 'extract_embedded_cover', True) else None)
            }
    except Exception as e:
        LOGGER.error(f"Audio metadata extraction failed: {str(e)}")
        return default_metadata(file_path)


async def extract_video_metadata(file_path: str) -> dict:
    """Extract metadata from video files"""
    try:
        if file_path.endswith(('.mp4', '.m4v', '.mov')):
            video = MP4(file_path)
            return {
                'title': video.get('\xa9nam', ['Unknown'])[0],
                'artist': video.get('\xa9ART', ['Unknown Artist'])[0],
                'duration': int(video.info.length) if hasattr(video, "info") else 0,
                'thumbnail': extract_cover_art(video, file_path) if getattr(bot_set, 'extract_embedded_cover', True) else None,
                'width': video.tags.get('width', [1920])[0] if hasattr(video, "tags") else 1920,
                'height': video.tags.get('height', [1080])[0] if hasattr(video, "tags") else 1080
            }
        else:
            return default_metadata(file_path)
    except Exception as e:
        LOGGER.error(f"Video metadata extraction failed for {file_path}: {str(e)}")
        return default_metadata(file_path)


async def extract_apple_metadata(file_path: str) -> dict:
    """
    Extract metadata from Apple Music files (audio or video)
    Args:
        file_path: Path to media file
    Returns:
        Metadata dictionary
    """
    try:
        if file_path.endswith('.m4a'):
            return await extract_audio_metadata(file_path)
        elif file_path.endswith(('.mp4', '.m4v', '.mov')):
            return await extract_video_metadata(file_path)
        else:
            # Handle other file types with mutagen
            audio = mutagen.File(file_path)
            return {
                'title': audio.get('title', ['Unknown'])[0],
                'artist': audio.get('artist', ['Unknown Artist'])[0],
                'album': audio.get('album', ['Unknown Album'])[0],
                'duration': int(audio.info.length),
                'thumbnail': (extract_cover_art(audio, file_path) if hasattr(audio, 'pictures') and getattr(bot_set, 'extract_embedded_cover', True) else None)
            }
    except Exception as e:
        LOGGER.error(f"Apple metadata extraction failed: {str(e)}")
        return default_metadata(file_path)


def extract_cover_art(media, file_path):
    """
    Extract cover art from audio/video file
    Args:
        media: Mutagen file object
        file_path: Path to media file
    Returns:
        Path to extracted cover art or None
    """
    try:
        # Handle MP4 cover art
        if 'covr' in media:
            cover_data = media['covr'][0]
            cover_path = f"{os.path.splitext(file_path)[0]}.jpg"
            with open(cover_path, 'wb') as f:
                f.write(cover_data)
            return cover_path
        
        # Handle ID3 tags (MP3)
        elif hasattr(media, 'pictures') and media.pictures:
            cover_data = media.pictures[0].data
            cover_path = f"{os.path.splitext(file_path)[0]}.jpg"
            with open(cover_path, 'wb') as f:
                f.write(cover_data)
            return cover_path
        
        # Handle FLAC/Vorbis comments
        elif 'metadata_block_picture' in media:
            for block in media.get('metadata_block_picture', []):
                try:
                    data = base64.b64decode(block)
                    pic = mutagen.flac.Picture(data)
                    if pic.type == 3:  # Front cover
                        cover_path = f"{os.path.splitext(file_path)[0]}.jpg"
                        with open(cover_path, 'wb') as f:
                            f.write(pic.data)
                        return cover_path
                except:
                    continue
    except Exception as e:
        LOGGER.error(f"Failed to extract cover art: {str(e)}")
    return None


def default_metadata(file_path):
    """Return default metadata when extraction fails"""
    return {
        'title': os.path.splitext(os.path.basename(file_path))[0],
        'artist': 'Unknown Artist',
        'album': 'Unknown Album',
        'duration': 0,
        'thumbnail': None
    }


async def create_apple_zip(directory: str, user_id: int, metadata: dict, progress: Optional[ProgressReporter] = None, cancel_event: asyncio.Event | None = None) -> str:
    """
    Create zip file with descriptive name for downloads
    Args:
        directory: Path to the content directory
        user_id: Telegram user ID
        metadata: Content metadata dictionary
    Returns:
        Path to the created zip file
    """
    # Determine content type and name
    content_type = metadata.get('type', 'album').capitalize()
    content_name = metadata.get('title', 'Unknown')
    provider = metadata.get('provider', 'Apple Music')
    
    # Sanitize the content name for filesystem safety
    safe_name = re.sub(r'[\\/*?:"<>|]', "", content_name)
    if bot_set.zip_name_use_underscores:
        safe_name = safe_name.replace(' ', '_')
    safe_name = safe_name[:100]  # Limit length
    
    # If name is empty after sanitization, use fallback
    if not safe_name.strip():
        safe_name = f"Apple_Music_{int(time.time())}"
        LOGGER.warning(f"Empty content name after sanitization, using fallback: {safe_name}")
    
    # Create descriptive filename based on content type
    if content_type.lower() == 'album':
        zip_name = f"[{provider}] {safe_name}"
    elif content_type.lower() == 'playlist':
        zip_name = f"[{provider}] {safe_name} (Playlist)"
    elif content_type.lower() == 'artist':
        zip_name = f"[{provider}] {safe_name} (Artist)"
    elif content_type.lower() == 'video':
        zip_name = f"[{provider}] {safe_name} (Video)"
    else:
        zip_name = f"[{provider}] {safe_name}"
    
    # Create zip path in the content's directory
    zip_dir = os.path.dirname(directory)
    zip_path = os.path.join(zip_dir, f"{zip_name}.zip")
    
    # Ensure unique filename
    counter = 1
    while os.path.exists(zip_path):
        zip_path = os.path.join(zip_dir, f"{zip_name}_{counter}.zip")
        counter += 1
    
    # Initialize progress
    if progress:
        await progress.set_stage("Zipping")
    
    # Count total files to zip
    total_files = 0
    for root, _, files in os.walk(directory):
        total_files += len(files)
    if progress and total_files:
        await progress.update_zip(0, total_files)
    
    # Create the zip file
    done_files = 0
    cancelled = False
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, _, files in os.walk(directory):
            for file in files:
                if cancel_event and cancel_event.is_set():
                    cancelled = True
                    break
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, directory)
                zipf.write(file_path, arcname)
                done_files += 1
                if progress:
                    await progress.update_zip(done_files, total_files)
            if cancelled:
                break
    if cancelled:
        try:
            if os.path.exists(zip_path):
                os.remove(zip_path)
        except Exception:
            pass
        raise asyncio.CancelledError()
    
    LOGGER.info(f"Created descriptive zip: {zip_path}")
    return zip_path


def _read_apple_config_paths(config_path: str | None = None) -> dict:
    """Read $HOME/amalac/config.yaml and return paths for alac/atmos/aac.
    Falls back to standard Apple Music directories under $HOME if not found.
    """
    try:
        home_dir = os.path.expanduser("~")
        cfg_path = config_path or os.path.join(home_dir, "amalac", "config.yaml")
        alac_dir = os.path.join(home_dir, "Music", "Apple Music", "alac")
        atmos_dir = os.path.join(home_dir, "Music", "Apple Music", "atmos")
        aac_dir = os.path.join(home_dir, "Music", "Apple Music", "aac")
        if os.path.exists(cfg_path):
            with open(cfg_path, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    if line.lower().startswith('alac-save-folder:'):
                        alac_dir = line.split(':', 1)[1].strip()
                    elif line.lower().startswith('atmos-save-folder:'):
                        atmos_dir = line.split(':', 1)[1].strip()
                    elif line.lower().startswith('aac-save-folder:'):
                        aac_dir = line.split(':', 1)[1].strip()
        return {
            'alac': os.path.expanduser(alac_dir),
            'atmos': os.path.expanduser(atmos_dir),
            'aac': os.path.expanduser(aac_dir),
        }
    except Exception as e:
        LOGGER.error(f"Failed to read Apple config paths: {str(e)}")
        return {}


def list_apple_output_files(extensions: tuple[str, ...] | None = None) -> list[str]:
    """List files from global Apple Music output directories defined in config.yaml."""
    exts = extensions or ('.m4a', '.flac', '.alac', '.mp4', '.m4v', '.mov')
    paths = _read_apple_config_paths()
    files: list[str] = []
    for key in ('alac', 'atmos', 'aac'):
        base = paths.get(key)
        if not base:
            continue
        for root, _, filenames in os.walk(base):
            for file in filenames:
                if file.lower().endswith(exts):
                    files.append(os.path.join(root, file))
    return files


def cleanup_apple_global():
    """Delete contents inside the alac/atmos/aac folders from the global Apple Music directory."""
    try:
        paths = _read_apple_config_paths()
        for key in ('alac', 'atmos', 'aac'):
            folder = paths.get(key)
            if not folder or not os.path.isdir(folder):
                continue
            for entry in os.listdir(folder):
                full_path = os.path.join(folder, entry)
                try:
                    if os.path.isdir(full_path):
                        shutil.rmtree(full_path, ignore_errors=True)
                    else:
                        os.remove(full_path)
                except Exception:
                    continue
        LOGGER.info("Apple global folders cleaned (contents deleted)")
    except Exception as e:
        LOGGER.error(f"Failed to clean Apple global folders: {str(e)}")
