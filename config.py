import os
import logging
from os import getenv
from dotenv import load_dotenv

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
LOGGER = logging.getLogger(__name__)

if not os.environ.get("ENV"):
    load_dotenv('.env', override=True)

class Config:
    # Telegram Configuration
    TG_BOT_TOKEN      = getenv("TG_BOT_TOKEN")                              # Bot token (e.g. "123456:ABC-DEF…")
    APP_ID            = int(getenv("APP_ID"))                              # API ID (int)
    API_HASH          = getenv("API_HASH")                                 # API hash (string)
    BOT_USERNAME      = getenv("BOT_USERNAME")                             # Bot username (e.g. "@mybot")
    ADMINS            = set(int(x) for x in getenv("ADMINS", "").replace(",", " ").split())  if getenv("ADMINS") else set()  
                                                                             # Admin IDs (space or comma separated ints)

    # Database Configuration
    DATABASE_URL      = getenv("DATABASE_URL")                            # PostgreSQL URL (e.g. "postgresql://user:pass@host:port/db")

    # Working Directory
    UPLOAD_MODE       = getenv("UPLOAD_MODE", "Telegram")                  # Telegram, RCLONE, or Local
    WORK_DIR          = getenv("WORK_DIR", "./bot/")                      # Bot working folder (path)
    DOWNLOADS_FOLDER  = getenv("DOWNLOADS_FOLDER", "DOWNLOADS")            # Folder name inside WORK_DIR
    LOCAL_STORAGE     = getenv("LOCAL_STORAGE", WORK_DIR + DOWNLOADS_FOLDER)  
                                                                            # Local storage path (path)
    # Base directory for downloads
    DOWNLOAD_BASE_DIR = LOCAL_STORAGE
    
    # Legacy Provider Directory (for Tidal, Qobuz, Deezer)
    LEGACY_WORK_DIR = getenv("LEGACY_WORK_DIR", "./bot/")
    LEGACY_DOWNLOADS_FOLDER = getenv("LEGACY_DOWNLOADS_FOLDER", "DOWNLOADS")
    LEGACY_DOWNLOAD_BASE_DIR = LEGACY_WORK_DIR + LEGACY_DOWNLOADS_FOLDER

    # File/Folder Naming
    PLAYLIST_NAME_FORMAT = getenv("PLAYLIST_NAME_FORMAT", "{title} - Playlist")  
                                                                            # e.g. "{title} - Playlist"
    TRACK_NAME_FORMAT    = getenv("TRACK_NAME_FORMAT", "{title} - {artist}")    
                                                                            # e.g. "{title} - {artist}"

    # Rclone/Index Configuration
    RCLONE_CONFIG     = getenv("RCLONE_CONFIG")                            # Path or URL to rclone.conf
    RCLONE_DEST       = getenv("RCLONE_DEST")                              # e.g. "remote:AppleMusic"
    INDEX_LINK        = getenv("INDEX_LINK")                               # Optional index base URL

    # Qobuz Configuration
    QOBUZ_EMAIL       = getenv("QOBUZ_EMAIL")                              # User email (string)
    QOBUZ_PASSWORD    = getenv("QOBUZ_PASSWORD")                           # Password (string)
    QOBUZ_USER        = int(getenv("QOBUZ_USER", 0))                       # User ID (int)
    QOBUZ_TOKEN       = getenv("QOBUZ_TOKEN")                              # Auth token (string)
    QOBUZ_QUALITY     = int(getenv("QOBUZ_QUALITY", 0))                    # 5, 6, 7, or 27

    # Deezer Configuration
    DEEZER_EMAIL      = getenv("DEEZER_EMAIL")                             # User email
    DEEZER_PASSWORD   = getenv("DEEZER_PASSWORD")                          # Password
    DEEZER_BF_SECRET  = getenv("DEEZER_BF_SECRET")                         # Secret token
    DEEZER_ARL        = getenv("DEEZER_ARL")                               # ARL cookie

    # Tidal Configuration
    ENABLE_TIDAL           = getenv("ENABLE_TIDAL", "False")              # True or False
    TIDAL_MOBILE           = getenv("TIDAL_MOBILE", "False")              # True or False
    TIDAL_MOBILE_TOKEN     = getenv("TIDAL_MOBILE_TOKEN")                 # Mobile token
    TIDAL_ATMOS_MOBILE_TOKEN = getenv("TIDAL_ATMOS_MOBILE_TOKEN")         # Atmos mobile token
    TIDAL_TV_TOKEN         = getenv("TIDAL_TV_TOKEN")                     # TV token
    TIDAL_TV_SECRET        = getenv("TIDAL_TV_SECRET")                    # TV secret
    TIDAL_CONVERT_M4A      = getenv("TIDAL_CONVERT_M4A", "False")         # True or False
    TIDAL_REFRESH_TOKEN    = getenv("TIDAL_REFRESH_TOKEN")                # Refresh token
    TIDAL_COUNTRY_CODE     = getenv("TIDAL_COUNTRY_CODE", "US")           # ISO country code (e.g. "US")
    TIDAL_QUALITY          = getenv("TIDAL_QUALITY")                      # LOW, HIGH, LOSSLESS, HI_RES
    TIDAL_SPATIAL          = getenv("TIDAL_SPATIAL")                      # OFF, ATMOS AC3 JOC, ATMOS AC4, Sony 360RA
    TIDAL_NG_DOWNLOAD_PATH = getenv("TIDAL_NG_DOWNLOAD_PATH")             # Optional: Custom download path for Tidal NG (legacy)
    # New: Env override for Tidal NG download_base_path (takes precedence over settings.json)
    TIDAL_NG_DOWNLOAD_BASE_PATH = getenv("TIDAL_NG_DOWNLOAD_BASE_PATH")

    # Concurrent Workers
    MAX_WORKERS      = int(getenv("MAX_WORKERS", 5))                       # Number of threads (int)

    # Apple Music Configuration
    DOWNLOADER_PATH   = getenv("DOWNLOADER_PATH", "/usr/src/app/downloader/am_downloader.sh")  
                                                                            # Downloader script path
    INSTALLER_PATH    = getenv("INSTALLER_PATH", "/usr/src/app/downloader/install_am_downloader.sh")  
                                                                            # Installer script path
    APPLE_DEFAULT_FORMAT = getenv("APPLE_DEFAULT_FORMAT", "alac")          # alac or atmos
    APPLE_ALAC_QUALITY    = int(getenv("APPLE_ALAC_QUALITY", 192000))     # 192000, 256000, 320000
    APPLE_ATMOS_QUALITY   = int(getenv("APPLE_ATMOS_QUALITY", 2768))      # Only 2768 for Atmos
    # Path to Apple Music downloader YAML config
    APPLE_CONFIG_YAML_PATH = getenv("APPLE_CONFIG_YAML_PATH", "/root/amalac/config.yaml")
    
    # Optional Settings (via /settings)
    BOT_PUBLIC            = getenv("BOT_PUBLIC", "False")                 # True or False
    ANTI_SPAM             = getenv("ANTI_SPAM", "OFF")                    # OFF, USER, or CHAT+
    ART_POSTER            = getenv("ART_POSTER", "False")                 # True or False
    PLAYLIST_SORT         = getenv("PLAYLIST_SORT", "False")              # True or False
    ARTIST_BATCH_UPLOAD   = getenv("ARTIST_BATCH_UPLOAD", "False")        # True or False
    PLAYLIST_CONCURRENT   = getenv("PLAYLIST_CONCURRENT", "False")        # True or False
    PLAYLIST_LINK_DISABLE = getenv("PLAYLIST_LINK_DISABLE", "False")      # True or False
    ALBUM_ZIP             = getenv("ALBUM_ZIP", "False")                  # True or False
    PLAYLIST_ZIP          = getenv("PLAYLIST_ZIP", "False")               # True or False
    ARTIST_ZIP            = getenv("ARTIST_ZIP", "False")                 # True or False
    RCLONE_LINK_OPTIONS   = getenv("RCLONE_LINK_OPTIONS", "Index")        # False, Index, RCLONE, or Both
    # New: control whether to extract embedded cover art from files (default OFF)
    EXTRACT_EMBEDDED_COVER = getenv("EXTRACT_EMBEDDED_COVER", "False")      # True or False

    # Apple Wrapper Scripts
    APPLE_WRAPPER_SETUP_PATH = getenv("APPLE_WRAPPER_SETUP_PATH", "/usr/src/app/downloader/setup_wrapper.sh")
    APPLE_WRAPPER_STOP_PATH  = getenv("APPLE_WRAPPER_STOP_PATH", "/usr/src/app/downloader/stop_wrapper.sh")
