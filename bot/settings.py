import os
import json
import base64
import requests
import subprocess

import bot.helpers.translations as lang

from config import Config
from bot.logger import LOGGER

from .helpers.database.pg_impl import set_db, download_history
from .helpers.qobuz.qopy import qobuz_api
from .helpers.deezer.dzapi import deezerapi
from .helpers.tidal.tidal_api import tidalapi
from .helpers.translations import lang_available


# Helper functions
def __getvalue__(var):
    value, _ = set_db.get_variable(var)
    return value if value else False

def _to_bool(value):
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() == 'true'

def __encrypt_string__(string):
    s = bytes(string, 'utf-8')
    s = base64.b64encode(s)
    return s

def __decrypt_string__(string):
    try:
        s = base64.b64decode(string)
        s = s.decode()
        return s
    except:
        return string

class BotSettings:
    def __init__(self):
        # Apple-only build: remove other providers
        self.deezer = False
        self.qobuz = False
        # Add this line to initialize can_enable_tidal
        self.can_enable_tidal = Config.ENABLE_TIDAL and Config.ENABLE_TIDAL.lower() == "true"
        # Runtime toggle for the legacy Tidal integration
        self.tidal_legacy_enabled = self.can_enable_tidal
        self.admins = Config.ADMINS
        self.apple = None  # Apple Music settings placeholder
        self.bot_username = (Config.BOT_USERNAME or "").lstrip("@")

        self.set_language()

        db_users, _ = set_db.get_variable('AUTH_USERS')
        self.auth_users = json.loads(db_users) if db_users else []
        db_chats, _ = set_db.get_variable('AUTH_CHATS')
        self.auth_chats = json.loads(db_chats) if db_chats else []

        self.rclone = False
        self.check_upload_mode()
        self.initialize_apple()

        spam, _ = set_db.get_variable('ANTI_SPAM')
        self.anti_spam = spam if spam else 'OFF'

        self.bot_public = _to_bool(__getvalue__('BOT_PUBLIC'))
        self.art_poster = _to_bool(__getvalue__('ART_POSTER'))
        self.playlist_sort = _to_bool(__getvalue__('PLAYLIST_SORT'))
        self.disable_sort_link = _to_bool(__getvalue__('PLAYLIST_LINK_DISABLE'))
        self.artist_batch = _to_bool(__getvalue__('ARTIST_BATCH_UPLOAD'))
        self.playlist_conc = _to_bool(__getvalue__('PLAYLIST_CONCURRENT'))
        # Queue mode toggle
        self.queue_mode = _to_bool(__getvalue__('QUEUE_MODE'))
        
        link_option, _ = set_db.get_variable('RCLONE_LINK_OPTIONS')
        self.link_options = link_option if self.rclone and link_option else 'False'

        # New: Rclone copy scope (FILE or FOLDER)
        rclone_scope, _ = set_db.get_variable('RCLONE_COPY_SCOPE')
        self.rclone_copy_scope = (rclone_scope or 'FILE').upper()

        # New: Rclone destination parts (remote and path)
        db_remote, _ = set_db.get_variable('RCLONE_REMOTE')
        db_dest_path, _ = set_db.get_variable('RCLONE_DEST_PATH')
        env_full = (Config.RCLONE_DEST or '').strip() if Config.RCLONE_DEST else ''
        # Back-compat: parse remote:path from env_full or DB full if present
        db_full, _ = set_db.get_variable('RCLONE_DEST')
        full = (db_full or env_full or '').strip()
        parsed_remote = ''
        parsed_path = ''
        if full and ':' in full:
            try:
                parsed_remote, parsed_path = full.split(':', 1)
            except Exception:
                parsed_remote = full.rstrip(':')
                parsed_path = ''
        # Prefer explicit DB parts, else parsed, else empty
        self.rclone_remote = (db_remote or parsed_remote or '').strip()
        self.rclone_dest_path = (db_dest_path if db_dest_path is not None else parsed_path).strip()
        # Compose effective destination
        if self.rclone_remote:
            if self.rclone_dest_path:
                self.rclone_dest = f"{self.rclone_remote}:{self.rclone_dest_path}"
            else:
                self.rclone_dest = f"{self.rclone_remote}:"
        else:
            self.rclone_dest = full

        self.album_zip = _to_bool(__getvalue__('ALBUM_ZIP'))
        self.playlist_zip = _to_bool(__getvalue__('PLAYLIST_ZIP'))
        self.artist_zip = _to_bool(__getvalue__('ARTIST_ZIP'))

        # New: Toggle for using underscores in zip filenames
        db_safe_zip, _ = set_db.get_variable('ZIP_NAME_USE_UNDERSCORES')
        if db_safe_zip is None:
            set_db.set_variable('ZIP_NAME_USE_UNDERSCORES', True)
            self.zip_name_use_underscores = True
        else:
            self.zip_name_use_underscores = _to_bool(db_safe_zip)

        # New: telegram video upload type
        video_doc, _ = set_db.get_variable('VIDEO_AS_DOCUMENT')
        self.video_as_document = bool(video_doc) if isinstance(video_doc, bool) else (str(video_doc).lower() == 'true')

        # New: whether to extract embedded cover artwork (persist in DB, default False)
        db_extract, _ = set_db.get_variable('EXTRACT_EMBEDDED_COVER')
        if db_extract is None or db_extract == '':
            # Seed DB with default if unset
            set_db.set_variable('EXTRACT_EMBEDDED_COVER', False)
            self.extract_embedded_cover = False
        else:
            self.extract_embedded_cover = _to_bool(db_extract)

        # Apple-specific zip toggles (separate from core)
        apple_album_zip, _ = set_db.get_variable('APPLE_ALBUM_ZIP')
        apple_playlist_zip, _ = set_db.get_variable('APPLE_PLAYLIST_ZIP')
        self.apple_album_zip = _to_bool(apple_album_zip)
        self.apple_playlist_zip = _to_bool(apple_playlist_zip)

        # Tidal NG specific zip toggles (separate from core)
        tng_album_zip, _ = set_db.get_variable('TIDAL_NG_ALBUM_ZIP')
        tng_playlist_zip, _ = set_db.get_variable('TIDAL_NG_PLAYLIST_ZIP')
        # default False when unset
        self.tidal_ng_album_zip = _to_bool(tng_album_zip)
        self.tidal_ng_playlist_zip = _to_bool(tng_playlist_zip)

        # Apple flags popup for /download (Apple-only)
        self.apple_flags_popup = _to_bool(__getvalue__('APPLE_FLAGS_POPUP'))

        # Preset cycling/toggle guards for panels
        acpe, _ = set_db.get_variable('APPLE_CYCLE_PRESETS_ENABLED')
        self.apple_cycle_presets_enabled = True if acpe is None else _to_bool(acpe)
        tncpe, _ = set_db.get_variable('TIDAL_NG_CYCLE_PRESETS_ENABLED')
        self.tidal_ng_cycle_presets_enabled = True if tncpe is None else _to_bool(tncpe)

        self.clients = []
        self.download_history = download_history

    def check_upload_mode(self):
        """Determine upload mode based on configuration"""
        if os.path.exists('rclone.conf'):
            self.rclone = True
        elif Config.RCLONE_CONFIG:
            if Config.RCLONE_CONFIG.startswith('http'):
                try:
                    rclone = requests.get(Config.RCLONE_CONFIG, allow_redirects=True)
                    if rclone.status_code == 200:
                        with open('rclone.conf', 'wb') as f:
                            f.write(rclone.content)
                        self.rclone = True
                    else:
                        LOGGER.error(f"Rclone config download failed: HTTP {rclone.status_code}")
                except Exception as e:
                    LOGGER.error(f"Rclone config download error: {str(e)}")
            else:
                if os.path.exists(Config.RCLONE_CONFIG):
                    self.rclone = True
        
        db_upload, _ = set_db.get_variable('UPLOAD_MODE')
        if self.rclone and db_upload == 'RCLONE':
            self.upload_mode = 'RCLONE'
        elif db_upload == 'Telegram' or db_upload == 'Local':
            self.upload_mode = db_upload
        else:
            self.upload_mode = 'Local'

    def initialize_apple(self):
        """Initialize Apple Music settings"""
        self.apple = {
            'downloader_path': Config.DOWNLOADER_PATH,
            'installer_path': Config.INSTALLER_PATH,
            'format': __getvalue__('APPLE_DEFAULT_FORMAT') or Config.APPLE_DEFAULT_FORMAT,
            'alac_quality': int(__getvalue__('APPLE_ALAC_QUALITY') or Config.APPLE_ALAC_QUALITY),
            'atmos_quality': int(__getvalue__('APPLE_ATMOS_QUALITY') or Config.APPLE_ATMOS_QUALITY)
        }
        
        # Ensure downloader is installed
        if not os.path.exists(Config.DOWNLOADER_PATH):
            LOGGER.warning("Apple Music downloader not found! Attempting installation...")
            try:
                subprocess.run([Config.INSTALLER_PATH], check=True)
                LOGGER.info("Apple Music downloader installed successfully")
            except Exception as e:
                LOGGER.error(f"Apple Music downloader installation failed: {str(e)}")

    # Apple-only build: remove other providers' login flows
    async def login_qobuz(self):
        """Initialize Qobuz client"""
        if Config.QOBUZ_EMAIL or Config.QOBUZ_USER:
            try:
                await qobuz_api.login()
                self.qobuz = qobuz_api
                self.clients.append(qobuz_api)
                quality, _ = set_db.get_variable("QOBUZ_QUALITY")
                if quality:
                    qobuz_api.quality = int(quality)
            except Exception as e:
                LOGGER.error(f"Qobuz login failed: {str(e)}")

    async def login_deezer(self):
        """Initialize Deezer client"""
        if Config.DEEZER_ARL or Config.DEEZER_EMAIL:
            if Config.DEEZER_BF_SECRET:
                login = await deezerapi.login()
                if login:
                    self.deezer = deezerapi
                    self.clients.append(deezerapi)
                    LOGGER.info(f"DEEZER : Subscription - {deezerapi.user['OFFER_NAME']}")
                else:
                    try:
                        await deezerapi.session.close()
                    except:
                        pass
            else:
                LOGGER.error('DEEZER : Check BF_SECRET and TRACK_URL_KEY')

    async def login_tidal(self):
        """Initialize Tidal client"""
        if not self.can_enable_tidal:
            return

        data = None
        if Config.TIDAL_REFRESH_TOKEN:
            data = {
                'user_id': None,
                'refresh_token': Config.TIDAL_REFRESH_TOKEN,
                'country_code': Config.TIDAL_COUNTRY_CODE
            }
        else:
            _, saved_info = set_db.get_variable("TIDAL_AUTH_DATA")
            if saved_info:
                try:
                    data = json.loads(__decrypt_string__(saved_info))
                except Exception as e:
                    LOGGER.error(f"TIDAL: Failed to parse saved auth data: {e}")
                    return

        if not data:
            return

        sub = await tidalapi.login_from_saved(data)
        if sub:
            LOGGER.info(f"TIDAL: Successfully loaded account - {sub}")

        if quality := __getvalue__('TIDAL_QUALITY'):
            tidalapi.quality = quality

        if spatial := __getvalue__('TIDAL_SPATIAL'):
            tidalapi.spatial = spatial

        self.tidal = tidalapi
        self.clients.append(tidalapi)

    async def save_tidal_login(self, session):
        """Save Tidal login session"""
        data = {
            "user_id": session.user_id,
            "refresh_token": session.refresh_token,
            "country_code": session.country_code
        }
        txt = json.dumps(data)
        set_db.set_variable("TIDAL_AUTH_DATA", 0, True, __encrypt_string__(txt))

    def set_language(self):
        """Set bot language"""
        db_lang, _ = set_db.get_variable('BOT_LANGUAGE')
        self.bot_lang = db_lang if db_lang else 'en'

        for item in lang_available:
            if item.__language__ == self.bot_lang:
                lang.s = item
                break

bot_set = BotSettings()
