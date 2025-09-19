import os
import json
import asyncio
import shutil
import re
import time
from pathlib import Path

from config import Config
from ..message import edit_message, send_message
from bot.logger import LOGGER
from ..database.pg_impl import download_history
from bot.helpers.utils import (
    extract_audio_metadata,
    extract_video_metadata,
)
from ..progress import ProgressReporter
from bot.helpers.tidal_ng.uploader import track_upload, album_upload, playlist_upload, music_video_upload
from bot.helpers.tidal_ng.utils import get_tidal_ng_download_base_path

# Define the path to the tidal-dl-ng CLI script
TIDAL_DL_NG_CLI_PATH = "/usr/src/app/tidal-dl-ng/tidal_dl_ng/cli.py"
# Define the path to the settings.json for the CLI tool
TIDAL_DL_NG_SETTINGS_PATH = "/root/.config/tidal_dl_ng/settings.json"


async def log_progress(stream, reporter: ProgressReporter):
    """Reads a stream from the subprocess and will eventually update the ProgressReporter."""
    # The parsing logic will be added in the next step. For now, we just log.
    while True:
        line = await stream.readline()
        if not line:
            break
        output = line.decode("utf-8").strip()
        LOGGER.info(f"[TidalDL-NG] {output}")
        try:
            # Look for track counter first (e.g., "[1/10]")
            track_match = re.search(r"\[(\d+)/(\d+)\]", output)
            if track_match:
                done = int(track_match.group(1))
                total = int(track_match.group(2))
                await reporter.set_total_tracks(total)
                await reporter.update_download(tracks_done=done)
                continue  # Skip to next line once we have a track update

            # Look for percentage as a fallback
            # Hiding percentage parsing to reduce API calls
            # pct_match = re.search(r'(\d+)%', output)
            # if pct_match:
            #     pct = int(pct_match.group(1))
            #     await reporter.update_download(percent=pct)

        except Exception as e:
            LOGGER.debug(f"Could not parse progress from Tidal NG line: {output} - {e}")


def get_content_id_from_url(url: str) -> str:
    """Extracts the content ID from a Tidal URL."""
    match = re.search(r"/(track|album|playlist|video)/(\d+)", url)
    return match.group(2) if match else "unknown"


async def start_tidal_ng(link: str, user: dict, options: dict = None):
    """
    Handles downloads using the tidal-dl-ng CLI tool in an isolated directory,
    and then uploads the result.
    """
    bot_msg = user.get("bot_msg")
    user_id = user.get("user_id")
    task_id = user.get("task_id", "no_id")

    # Create a unique temporary directory for this download task
    temp_download_path = os.path.join(Config.LOCAL_STORAGE, str(user_id), f"tidal_ng_temp_{task_id}")
    os.makedirs(temp_download_path, exist_ok=True)

    original_settings = None
    settings_backup = None

    # Initialize progress reporter
    label = "Tidal NG"
    reporter = ProgressReporter(bot_msg, label=label, show_system_stats=False)
    await reporter.set_stage("Downloading")

    try:
        # --- Backup and modify settings.json ---
        try:
            with open(TIDAL_DL_NG_SETTINGS_PATH, "r") as f:
                settings_backup = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            settings_backup = {}

        temp_settings = settings_backup.copy()
        temp_settings["download_base_path"] = temp_download_path

        # Ensure the directory for the settings file exists
        os.makedirs(os.path.dirname(TIDAL_DL_NG_SETTINGS_PATH), exist_ok=True)
        with open(TIDAL_DL_NG_SETTINGS_PATH, "w") as f:
            json.dump(temp_settings, f, indent=4)

        # --- Execute Download ---
        env = os.environ.copy()
        env["FFMPEG_PATH"] = "/usr/bin/ffmpeg"
        cmd = ["python", TIDAL_DL_NG_CLI_PATH, "dl", link]
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        await asyncio.gather(
            log_progress(process.stdout, reporter),
            log_progress(process.stderr, reporter),
        )
        await process.wait()

        if process.returncode != 0:
            raise Exception("Tidal-NG download process failed.")

        # --- Collect Files from the temporary directory ---
        await reporter.set_stage("Processing")
        downloaded_files = []
        for root, _, files in os.walk(temp_download_path):
            for file in files:
                downloaded_files.append(os.path.join(root, file))

        if not downloaded_files:
            raise Exception("No files were downloaded into the temporary directory.")

        # --- Metadata Extraction ---
        items = []
        for file_path in downloaded_files:
            try:
                # Use a combined metadata dictionary for quality and other tags
                metadata = {}
                if file_path.lower().endswith((".mp4", ".m4v")):
                    metadata.update(await extract_video_metadata(file_path))
                else:
                    metadata.update(await extract_audio_metadata(file_path))

                metadata["filepath"] = file_path
                metadata["provider"] = "Tidal NG"
                # Add quality from original settings for later use
                metadata["quality"] = settings_backup.get("quality_audio", "N/A")
                items.append(metadata)

            except Exception as e:
                LOGGER.error(f"Metadata extraction failed for {file_path}: {str(e)}")

        if not items:
            raise Exception("Metadata extraction failed for all downloaded files.")

        # --- Determine Content Type ---
        inferred_type = None
        # Simplified logic: if more than one file, it's a collection (album/playlist)
        if len(items) > 1:
            # Check if all tracks belong to the same album
            album_titles = {item.get("album") for item in items if item.get("album")}
            if len(album_titles) == 1:
                inferred_type = "album"
            else:
                inferred_type = "playlist"
        elif items:
            # Single item
            if items[0]["filepath"].lower().endswith((".mp4", ".m4v")):
                inferred_type = "video"
            else:
                inferred_type = "track"

        content_type = inferred_type or "track"

        # --- Prepare Metadata for Uploader ---
        # Find the actual content folder, which is the common path of all downloaded files.
        content_folder = temp_download_path
        if content_type in ["album", "playlist"] and downloaded_files:
            common_path = os.path.commonpath(downloaded_files)
            # If the common path is a directory, that's our content folder.
            if os.path.isdir(common_path):
                content_folder = common_path
            else:
                # If it's a file path (e.g., for single track downloads), the content folder is its parent.
                content_folder = os.path.dirname(common_path)

        resolved_title = "Unknown"
        if content_type == "album":
            resolved_title = items[0].get("album", "Unknown Album")
        elif content_type == "playlist":
             # Use the URL to derive a playlist name if possible
            match = re.search(r"/playlist/([a-fA-F0-9-]+)", link)
            if match:
                resolved_title = f"Playlist {match.group(1)}"
            else:
                resolved_title = "Playlist"
        else: # track or video
            resolved_title = items[0].get("title", "Unknown Track")

        upload_meta = {
            "success": True,
            "type": content_type,
            "items": items,
            "folderpath": str(content_folder),
            "provider": "Tidal NG",
            "title": resolved_title,
            "artist": items[0].get("artist"),
            "poster_msg": bot_msg,
        }

        # --- Record History ---
        content_id = get_content_id_from_url(link)
        download_history.record_download(
            user_id=user.get("user_id"),
            provider="Tidal NG",
            content_type=content_type,
            content_id=content_id,
            title=upload_meta["title"],
            artist=upload_meta["artist"],
            quality=settings_backup.get("quality_audio", "N/A"),
        )

        # --- Upload ---
        if content_type == "track":
            await track_upload(items[0], user, base_path=temp_download_path)
        elif content_type == "video":
            await music_video_upload(items[0], user, base_path=temp_download_path)
        elif content_type == "album":
            await album_upload(upload_meta, user, base_path=temp_download_path)
        elif content_type == "playlist":
            await playlist_upload(upload_meta, user, base_path=temp_download_path)

    except Exception as e:
        LOGGER.error(f"An error occurred in start_tidal_ng: {e}", exc_info=True)
        await edit_message(bot_msg, f"❌ **Fatal Error:** {e}")

    finally:
        # --- Restore settings.json and cleanup ---
        if settings_backup is not None:
            try:
                with open(TIDAL_DL_NG_SETTINGS_PATH, "w") as f:
                    json.dump(settings_backup, f, indent=4)
                LOGGER.info("Tidal-NG settings.json restored to original state.")
            except Exception as e:
                LOGGER.error(f"Failed to restore Tidal-NG settings.json: {e}")

        if os.path.exists(temp_download_path):
            shutil.rmtree(temp_download_path, ignore_errors=True)
            LOGGER.info(f"Cleaned up temporary directory: {temp_download_path}")
