import bot.helpers.translations as lang
import asyncio

from pyrogram import Client, filters
from pyrogram.types import CallbackQuery, Message, InlineKeyboardButton, InlineKeyboardMarkup

from config import Config

from ..settings import bot_set
from ..helpers.buttons.settings import *
from ..helpers.database.pg_impl import set_db, user_set_db
from ..helpers.tidal.tidal_api import tidalapi

from ..helpers.message import edit_message, check_user
from ..helpers.state import conversation_state
import os
import json


# Custom filter to check if a user is in the tidal NG file import state
async def is_awaiting_tidal_ng_file_filter(_, __, message: Message):
    if not message.from_user:
        return False
    state = await conversation_state.get(message.from_user.id)
    return state and state.get('stage') == "awaiting_tidal_ng_file"

# Apply the custom filter and set a high priority group (-1) to run before the default handlers
@Client.on_message(filters.document & filters.private & filters.create(is_awaiting_tidal_ng_file_filter), group=-1)
async def handle_tidal_ng_config_upload(c: Client, msg: Message):
    user_id = msg.from_user.id
    state = await conversation_state.get(user_id)
    # The state check is now handled by the filter, so we can remove it from here.

    if not msg.document:
        return

    target_dir = state.get('data', {}).get('target_dir')
    if not target_dir:
        await c.send_message(user_id, "❌ An error occurred. The target directory was not set. Please start over.")
        await conversation_state.clear(user_id)
        return

    original_filename = msg.document.file_name
    target_path = os.path.join(target_dir, original_filename)

    progress_msg = await c.send_message(user_id, f"Importing `{original_filename}`...")
    temp_path = None
    try:
        temp_path = await c.download_media(msg)
        os.makedirs(target_dir, exist_ok=True)
        os.replace(temp_path, target_path)
        os.chmod(target_path, 0o666)
        await edit_message(progress_msg, f"✅ **Import Successful!**\nFile `{original_filename}` has been saved to `{target_dir}`.")

    except Exception as e:
        await edit_message(progress_msg, f"❌ **An Error Occurred:**\n`{str(e)}`")
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)
        await conversation_state.clear(user_id)


# Custom filter to check if a user is in the Apple Music file import state
async def is_awaiting_apple_music_file_filter(_, __, message: Message):
    if not message.from_user:
        return False
    state = await conversation_state.get(message.from_user.id)
    return state and state.get('stage') == "awaiting_apple_music_file"

@Client.on_message(filters.document & filters.private & filters.create(is_awaiting_apple_music_file_filter), group=-1)
async def handle_apple_music_file_upload(c: Client, msg: Message):
    user_id = msg.from_user.id
    state = await conversation_state.get(user_id)

    if not msg.document:
        return

    target_dir = state.get('data', {}).get('target_dir')
    if not target_dir:
        await c.send_message(user_id, "❌ An error occurred. The target directory was not set. Please start over.")
        await conversation_state.clear(user_id)
        return

    original_filename = msg.document.file_name
    target_path = os.path.join(target_dir, original_filename)

    progress_msg = await c.send_message(user_id, f"Importing `{original_filename}` to `{target_dir}`...")
    temp_path = None
    try:
        temp_path = await c.download_media(msg)
        os.makedirs(target_dir, exist_ok=True)
        os.replace(temp_path, target_path)
        # No chmod needed for this directory, unlike the tidal-dl-ng config
        await edit_message(progress_msg, f"✅ **Import Successful!**\nFile `{original_filename}` has been saved to `{target_dir}`.")

    except Exception as e:
        await edit_message(progress_msg, f"❌ **An Error Occurred:**\n`{str(e)}`")
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)
        await conversation_state.clear(user_id)


# Custom filter for apple_yaml_set stage
async def is_awaiting_apple_yaml_filter(_, __, message: Message):
    if not message.from_user:
        return False
    state = await conversation_state.get(message.from_user.id)
    return state and state.get('stage') == "apple_yaml_set"

@Client.on_message(filters.text & filters.private & filters.create(is_awaiting_apple_yaml_filter), group=-2)
async def handle_apple_yaml_set(c: Client, msg: Message):
    user_id = msg.from_user.id
    state = await conversation_state.get(user_id)
    key_to_set = state.get('data', {}).get('key')

    if not key_to_set:
        await msg.reply_text("❌ An error occurred. The key to set was not found. Please start over.")
        await conversation_state.clear(user_id)
        return

    value_to_set = msg.text.strip()

    # Handle cancellation
    if value_to_set.lower() == "/cancel":
        await conversation_state.clear(user_id)
        await msg.reply_text("✅ Operation cancelled.")
        return

    try:
        _yaml_set(key_to_set, value_to_set)
        await msg.reply_text(f"✅ Successfully updated <code>{key_to_set}</code>.")
    except Exception as e:
        await msg.reply_text(f"❌ An error occurred while updating the configuration: {e}")
    finally:
        await conversation_state.clear(user_id)


@Client.on_callback_query(filters.regex(pattern=r"^providerPanel"))
async def provider_cb(c, cb: CallbackQuery):
    if await check_user(cb.from_user.id, restricted=True):
        buttons = []
        # Always show Apple Music button
        buttons.append([
            InlineKeyboardButton("🍎 Apple Music", callback_data="appleP")
        ])

        # Conditionally show other providers
        if bot_set.qobuz:
            buttons.append([
                InlineKeyboardButton(lang.s.QOBUZ, callback_data="qbP")
            ])
        if bot_set.deezer:
            buttons.append([
                InlineKeyboardButton(lang.s.DEEZER, callback_data="dzP")
            ])
        if bot_set.can_enable_tidal:
            buttons.append([
                InlineKeyboardButton(lang.s.TIDAL, callback_data="tdP")
            ])
            buttons.append([
                InlineKeyboardButton("Tidal DL NG", callback_data="tidalNgP")
            ])

        buttons += [
            [InlineKeyboardButton(lang.s.MAIN_MENU_BUTTON, callback_data="main_menu")],
            [InlineKeyboardButton(lang.s.CLOSE_BUTTON, callback_data="close")]
        ]
        
        await edit_message(
            cb.message,
            lang.s.PROVIDERS_PANEL,
            InlineKeyboardMarkup(buttons)
        )


#----------------
# APPLE MUSIC
#----------------
@Client.on_callback_query(filters.regex(pattern=r"^appleP"))
async def apple_cb(c, cb: CallbackQuery):
    if await check_user(cb.from_user.id, restricted=True):
        formats = {
            'alac': 'ALAC',
            'atmos': 'Dolby Atmos'
        }
        current = Config.APPLE_DEFAULT_FORMAT
        formats[current] += ' ✅'
        # Build Apple panel buttons dynamically to include Apple-specific zip toggles
        from ..settings import bot_set as _bs
        zip_album_label = f"Zip Albums (Apple): {'ON ✅' if getattr(_bs, 'apple_album_zip', False) else 'OFF'}"
        zip_playlist_label = f"Zip Playlists (Apple): {'ON ✅' if getattr(_bs, 'apple_playlist_zip', False) else 'OFF'}"

        # Read YAML for labels
        try:
            from .config_yaml import _read_yaml_lines, _get_key, YAML_PATH
            lines = _read_yaml_lines(YAML_PATH)
        except Exception:
            lines = []
        def gv(k: str, d: str = "-"):
            try:
                v = _get_key(lines, k)
                return (v or d).strip('"')
            except Exception:
                return d
        lab_cover_size = f"Cover Size: {gv('cover-size','5000x5000')}"
        lab_cover_fmt = f"Cover Format: {gv('cover-format','jpg')}"
        lab_embed_cover = f"Embed Cover: {'ON ✅' if gv('embed-cover','true').lower()=='true' else 'OFF'}"
        lab_embed_lrc = f"Embed Lyrics: {'ON ✅' if gv('embed-lrc','true').lower()=='true' else 'OFF'}"
        lab_save_lrc = f"Save Lyrics File: {'ON ✅' if gv('save-lrc-file','false').lower()=='true' else 'OFF'}"
        lab_lrc_type = f"Lyrics Type: {gv('lrc-type','lyrics')}"
        lab_lrc_fmt = f"Lyrics Format: {gv('lrc-format','lrc')}"
        lab_save_artist = f"Save Artist Cover: {'ON ✅' if gv('save-artist-cover','false').lower()=='true' else 'OFF'}"
        lab_anim_aw = f"Animated Artwork: {'ON ✅' if gv('save-animated-artwork','false').lower()=='true' else 'OFF'}"
        lab_emby_anim = f"Emby Animated: {'ON ✅' if gv('emby-animated-artwork','false').lower()=='true' else 'OFF'}"
        lab_mv_audio = f"MV Audio: {gv('mv-audio-type','atmos')}"
        lab_mv_max = f"MV Max: {gv('mv-max','2160')}"
        lab_dl_cov_pl = f"DL AlbumCover for Playlist: {'ON ✅' if gv('dl-albumcover-for-playlist','false').lower()=='true' else 'OFF'}"
        lab_use_songinfo = f"Use Songinfo for Playlist: {'ON ✅' if gv('use-songinfo-for-playlist','false').lower()=='true' else 'OFF'}"
        lab_limit_max = f"Limit Max: {gv('limit-max','200')}"
        lab_aac_type = f"AAC Type: {gv('aac-type','aac-lc')}"
        lab_alac_max = f"ALAC Max: {gv('alac-max','192000')}"
        lab_atmos_max = f"ATMOS Max: {gv('atmos-max','2768')}"
        lab_m3u8_mode = f"M3U8 Mode: {gv('get-m3u8-mode','hires')}"
        lab_language = f"Language: {gv('language','-')}"
        lab_storefront = f"Storefront: {gv('storefront','US')}"
        lab_album_fmt = f"Album Folder: {gv('album-folder-format','{AlbumName}')}"
        lab_playlist_fmt = f"Playlist Folder: {gv('playlist-folder-format','{PlaylistName}')}"
        lab_song_fmt = f"Song File: {gv('song-file-format','{SongNumer}. {SongName}')}"

        buttons = []
        # Interactive editing removed; use /config_set instead
        # Top-level guard toggle for cycling presets
        try:
            from ..settings import bot_set as _bs_guard
            guard_label = f"Preset Buttons: {'ON ✅' if getattr(_bs_guard, 'apple_cycle_presets_enabled', True) else 'OFF'}"
        except Exception:
            guard_label = "Preset Buttons: ON ✅"
        buttons.append([InlineKeyboardButton(guard_label, callback_data="appleTogglePresetGuard")])
        from ..settings import bot_set as _bs_guard2
        if getattr(_bs_guard2, 'apple_cycle_presets_enabled', True):
            for fmt, label in formats.items():
                buttons.append([InlineKeyboardButton(label, callback_data=f"appleF_{fmt}")])
            buttons.append([InlineKeyboardButton("Quality Settings", callback_data="appleQ")])
        buttons.append([
            InlineKeyboardButton("🧩 Setup Wrapper", callback_data="appleSetup"),
            InlineKeyboardButton("⏹️ Stop Wrapper", callback_data="appleStop")
        ])
        buttons.append([
            InlineKeyboardButton("📂 Manage Files", callback_data="fm_browse:/root/amalac/:appleP"),
            InlineKeyboardButton("📂 Import File", callback_data="appleImportFile")
        ])
        buttons.append([
            InlineKeyboardButton(zip_album_label, callback_data="appleToggleZipAlbum"),
            InlineKeyboardButton(zip_playlist_label, callback_data="appleToggleZipPlaylist")
        ])
        # Artwork & cover controls
        if getattr(_bs_guard2, 'apple_cycle_presets_enabled', True):
            buttons.append([
                InlineKeyboardButton(lab_cover_size, callback_data="appleCycleCoverSize"),
                InlineKeyboardButton(lab_cover_fmt, callback_data="appleCycleCoverFormat"),
            ])
        if getattr(_bs_guard2, 'apple_cycle_presets_enabled', True):
            buttons.append([
                InlineKeyboardButton(lab_embed_cover, callback_data="appleToggleEmbedCover"),
                InlineKeyboardButton(lab_save_artist, callback_data="appleToggleSaveArtistCover"),
            ])
        # Lyrics controls
        if getattr(_bs_guard2, 'apple_cycle_presets_enabled', True):
            buttons.append([
                InlineKeyboardButton(lab_lrc_type, callback_data="appleCycleLyricsType"),
                InlineKeyboardButton(lab_lrc_fmt, callback_data="appleCycleLyricsFormat"),
            ])
            buttons.append([
                InlineKeyboardButton(lab_embed_lrc, callback_data="appleToggleEmbedLrc"),
                InlineKeyboardButton(lab_save_lrc, callback_data="appleToggleSaveLrc"),
            ])
        # Animated artwork / MV
        if getattr(_bs_guard2, 'apple_cycle_presets_enabled', True):
            buttons.append([
                InlineKeyboardButton(lab_anim_aw, callback_data="appleToggleAnimatedArtwork"),
                InlineKeyboardButton(lab_emby_anim, callback_data="appleToggleEmbyAnimatedArtwork"),
            ])
        if getattr(_bs_guard2, 'apple_cycle_presets_enabled', True):
            buttons.append([
                InlineKeyboardButton(lab_mv_audio, callback_data="appleCycleMvAudioType"),
                InlineKeyboardButton(lab_mv_max, callback_data="appleCycleMvMax"),
            ])
        # Playlist enhancements
        if getattr(_bs_guard2, 'apple_cycle_presets_enabled', True):
            buttons.append([
                InlineKeyboardButton(lab_dl_cov_pl, callback_data="appleToggleDlAlbumCoverPlaylist"),
                InlineKeyboardButton(lab_use_songinfo, callback_data="appleToggleUseSonginfoPlaylist"),
            ])
        # Concurrency and naming presets
        if getattr(_bs_guard2, 'apple_cycle_presets_enabled', True):
            buttons.append([
                InlineKeyboardButton(lab_limit_max, callback_data="appleCycleLimitMax"),
                InlineKeyboardButton("Workers Info", callback_data="noop"),
            ])
        if getattr(_bs_guard2, 'apple_cycle_presets_enabled', True):
            buttons.append([
                InlineKeyboardButton(lab_album_fmt, callback_data="appleCycleAlbumFolderFormat"),
                InlineKeyboardButton(lab_playlist_fmt, callback_data="appleCyclePlaylistFolderFormat"),
            ])
            buttons.append([
                InlineKeyboardButton(lab_song_fmt, callback_data="appleCycleSongFileFormat"),
            ])
        # Audio pipeline and network options
        if getattr(_bs_guard2, 'apple_cycle_presets_enabled', True):
            buttons.append([
                InlineKeyboardButton(lab_aac_type, callback_data="appleCycleAacType"),
                InlineKeyboardButton(lab_alac_max, callback_data="appleCycleAlacMax"),
            ])
            buttons.append([
                InlineKeyboardButton(lab_atmos_max, callback_data="appleCycleAtmosMax"),
                InlineKeyboardButton(lab_m3u8_mode, callback_data="appleCycleM3u8Mode"),
            ])
        # Apple flags popup toggle
        try:
            from ..settings import bot_set as _bs2
            flag_label = f"Flags Popup: {'ON ✅' if getattr(_bs2, 'apple_flags_popup', False) else 'OFF'}"
        except Exception:
            flag_label = "Flags Popup: OFF"
        buttons.append([
            InlineKeyboardButton(flag_label, callback_data="appleToggleFlagsPopup")
        ])
        # Update media-user-token flow
        buttons.append([
            InlineKeyboardButton("🔐 Update media-user-token", callback_data="appleUpdateMediaUserToken")
        ])
        buttons.append([
            InlineKeyboardButton(lab_language, callback_data="applePromptLanguage"),
            InlineKeyboardButton(lab_storefront, callback_data="applePromptStorefront"),
        ])
        buttons.append([InlineKeyboardButton("🔙 Back", callback_data="providerPanel")])

        await edit_message(
            cb.message,
            "🍎 **Apple Music Settings**\n\n"
            "Control formats, quality, wrapper, and Apple-specific zip behavior.",
            InlineKeyboardMarkup(buttons)
        )


    # Interactive editing removed; use /config_set instead


@Client.on_callback_query(filters.regex(pattern=r"^appleF"))
async def apple_format_cb(c, cb: CallbackQuery):
    if await check_user(cb.from_user.id, restricted=True):
        format_type = cb.data.split('_')[1]
        # Update configuration
        set_db.set_variable('APPLE_DEFAULT_FORMAT', format_type)
        Config.APPLE_DEFAULT_FORMAT = format_type
        await apple_cb(c, cb)


@Client.on_callback_query(filters.regex(pattern=r"^appleQ"))
async def apple_quality_cb(c, cb: CallbackQuery):
    if await check_user(cb.from_user.id, restricted=True):
        qualities = {
            'alac': ['192000', '256000', '320000'],
            'atmos': ['2768', '3072', '3456']
        }
        current_format = Config.APPLE_DEFAULT_FORMAT
        current_quality = getattr(Config, f'APPLE_{current_format.upper()}_QUALITY')
        
        # Create quality buttons
        buttons = []
        for quality in qualities[current_format]:
            label = f"{quality} kbps"
            if quality == current_quality:
                label += " ✅"
            buttons.append([InlineKeyboardButton(label, callback_data=f"appleSQ_{current_format}_{quality}")])
        
        buttons.append([InlineKeyboardButton("🔙 Back", callback_data="appleP")])
        
        await edit_message(
            cb.message,
            f"⚙️ **{current_format.upper()} Quality Settings**\n\n"
            "Select the maximum quality for downloads:",
            InlineKeyboardMarkup(buttons)
        )


@Client.on_callback_query(filters.regex(pattern=r"^appleSQ"))
async def apple_set_quality_cb(c, cb: CallbackQuery):
    if await check_user(cb.from_user.id, restricted=True):
        _, format_type, quality = cb.data.split('_')
        # Update configuration
        set_db.set_variable(f'APPLE_{format_type.upper()}_QUALITY', quality)
        setattr(Config, f'APPLE_{format_type.upper()}_QUALITY', quality)
        await apple_quality_cb(c, cb)


@Client.on_callback_query(filters.regex(pattern=r"^appleToggleZipAlbum$"))
async def apple_toggle_zip_album(c: Client, cb: CallbackQuery):
    if await check_user(cb.from_user.id, restricted=True):
        try:
            from ..settings import bot_set
            from ..helpers.database.pg_impl import set_db
            bot_set.apple_album_zip = not bool(getattr(bot_set, 'apple_album_zip', False))
            set_db.set_variable('APPLE_ALBUM_ZIP', bot_set.apple_album_zip)
        except Exception:
            pass
        await apple_cb(c, cb)


@Client.on_callback_query(filters.regex(pattern=r"^appleToggleZipPlaylist$"))
async def apple_toggle_zip_playlist(c: Client, cb: CallbackQuery):
    if await check_user(cb.from_user.id, restricted=True):
        try:
            from ..settings import bot_set
            from ..helpers.database.pg_impl import set_db
            bot_set.apple_playlist_zip = not bool(getattr(bot_set, 'apple_playlist_zip', False))
            set_db.set_variable('APPLE_PLAYLIST_ZIP', bot_set.apple_playlist_zip)
        except Exception:
            pass
        await apple_cb(c, cb)


def _yaml_set(key: str, value: str):
    from .config_yaml import _read_yaml_lines, _set_key, _write_yaml_lines, _backup, YAML_PATH
    lines = _read_yaml_lines(YAML_PATH)
    _backup(YAML_PATH)
    new_lines = _set_key(lines, key, value)
    _write_yaml_lines(YAML_PATH, new_lines)


def _yaml_toggle_bool(key: str, default_true: bool = True):
    from .config_yaml import _read_yaml_lines, _get_key
    cur_lines = _read_yaml_lines(Config.APPLE_CONFIG_YAML_PATH)
    cur = (_get_key(cur_lines, key) or ("true" if default_true else "false")).split("#",1)[0].strip().lower()
    newv = "false" if cur == "true" else "true"
    _yaml_set(key, newv)


@Client.on_callback_query(filters.regex(pattern=r"^appleCycleCoverSize$"))
async def apple_cycle_cover_size(c: Client, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True): return
    try:
        sizes = ["1000x1000", "3000x3000", "5000x5000"]
        from .config_yaml import _read_yaml_lines, _get_key
        lines = _read_yaml_lines(Config.APPLE_CONFIG_YAML_PATH)
        cur = (_get_key(lines, 'cover-size') or '5000x5000').strip('"')
        try:
            idx = sizes.index(cur)
        except Exception:
            idx = -1
        _yaml_set('cover-size', sizes[(idx + 1) % len(sizes)])
    except Exception:
        pass
    await apple_cb(c, cb)


@Client.on_callback_query(filters.regex(pattern=r"^appleUpdateMediaUserToken$"))
async def apple_update_media_user_token(c: Client, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True):
        return
    try:
        await conversation_state.start(cb.from_user.id, "apple_yaml_set", {"key": "media-user-token", "chat_id": cb.message.chat.id})
        await edit_message(cb.message, "Send your <code>media-user-token</code> as a message now. You can /cancel to abort.")
    except Exception:
        pass

@Client.on_callback_query(filters.regex(pattern=r"^appleToggleFlagsPopup$"))
async def apple_toggle_flags_popup(c: Client, cb: CallbackQuery):
    if await check_user(cb.from_user.id, restricted=True):
        try:
            from ..settings import bot_set
            from ..helpers.database.pg_impl import set_db
            bot_set.apple_flags_popup = not bool(getattr(bot_set, 'apple_flags_popup', False))
            set_db.set_variable('APPLE_FLAGS_POPUP', bot_set.apple_flags_popup)
        except Exception:
            pass
        await apple_cb(c, cb)


@Client.on_callback_query(filters.regex(pattern=r"^appleTogglePresetGuard$"))
async def apple_toggle_preset_guard(c: Client, cb: CallbackQuery):
    if await check_user(cb.from_user.id, restricted=True):
        try:
            from ..settings import bot_set
            from ..helpers.database.pg_impl import set_db
            bot_set.apple_cycle_presets_enabled = not bool(getattr(bot_set, 'apple_cycle_presets_enabled', True))
            set_db.set_variable('APPLE_CYCLE_PRESETS_ENABLED', bot_set.apple_cycle_presets_enabled)
        except Exception:
            pass
        await apple_cb(c, cb)

@Client.on_callback_query(filters.regex(pattern=r"^appleCycleCoverFormat$"))
async def apple_cycle_cover_format(c: Client, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True): return
    try:
        fmts = ["jpg", "png", "original"]
        from .config_yaml import _read_yaml_lines, _get_key
        lines = _read_yaml_lines(Config.APPLE_CONFIG_YAML_PATH)
        cur = (_get_key(lines, 'cover-format') or 'jpg').strip('"')
        try:
            idx = fmts.index(cur)
        except Exception:
            idx = -1
        _yaml_set('cover-format', fmts[(idx + 1) % len(fmts)])
    except Exception:
        pass
    await apple_cb(c, cb)


@Client.on_callback_query(filters.regex(pattern=r"^appleToggleEmbedCover$"))
async def apple_toggle_embed_cover(c: Client, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True): return
    try:
        _yaml_toggle_bool('embed-cover', True)
    except Exception:
        pass
    await apple_cb(c, cb)


@Client.on_callback_query(filters.regex(pattern=r"^appleToggleSaveArtistCover$"))
async def apple_toggle_save_artist_cover(c: Client, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True): return
    try:
        _yaml_toggle_bool('save-artist-cover', False)
    except Exception:
        pass
    await apple_cb(c, cb)


@Client.on_callback_query(filters.regex(pattern=r"^appleCycleLyricsType$"))
async def apple_cycle_lyrics_type(c: Client, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True): return
    try:
        opts = ["lyrics", "syllable-lyrics"]
        from .config_yaml import _read_yaml_lines, _get_key
        lines = _read_yaml_lines(Config.APPLE_CONFIG_YAML_PATH)
        cur = (_get_key(lines, 'lrc-type') or 'lyrics').strip('"')
        try:
            idx = opts.index(cur)
        except Exception:
            idx = -1
        _yaml_set('lrc-type', opts[(idx + 1) % len(opts)])
    except Exception:
        pass
    await apple_cb(c, cb)


@Client.on_callback_query(filters.regex(pattern=r"^appleCycleLyricsFormat$"))
async def apple_cycle_lyrics_format(c: Client, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True): return
    try:
        opts = ["lrc", "ttml"]
        from .config_yaml import _read_yaml_lines, _get_key
        lines = _read_yaml_lines(Config.APPLE_CONFIG_YAML_PATH)
        cur = (_get_key(lines, 'lrc-format') or 'lrc').strip('"')
        try:
            idx = opts.index(cur)
        except Exception:
            idx = -1
        _yaml_set('lrc-format', opts[(idx + 1) % len(opts)])
    except Exception:
        pass
    await apple_cb(c, cb)


@Client.on_callback_query(filters.regex(pattern=r"^appleToggleEmbedLrc$"))
async def apple_toggle_embed_lrc(c: Client, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True): return
    try:
        _yaml_toggle_bool('embed-lrc', True)
    except Exception:
        pass
    await apple_cb(c, cb)


@Client.on_callback_query(filters.regex(pattern=r"^appleToggleSaveLrc$"))
async def apple_toggle_save_lrc(c: Client, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True): return
    try:
        _yaml_toggle_bool('save-lrc-file', False)
    except Exception:
        pass
    await apple_cb(c, cb)


@Client.on_callback_query(filters.regex(pattern=r"^appleToggleAnimatedArtwork$"))
async def apple_toggle_animated_artwork(c: Client, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True): return
    try:
        _yaml_toggle_bool('save-animated-artwork', False)
    except Exception:
        pass
    await apple_cb(c, cb)


@Client.on_callback_query(filters.regex(pattern=r"^appleToggleEmbyAnimatedArtwork$"))
async def apple_toggle_emby_animated_artwork(c: Client, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True): return
    try:
        _yaml_toggle_bool('emby-animated-artwork', False)
    except Exception:
        pass
    await apple_cb(c, cb)


@Client.on_callback_query(filters.regex(pattern=r"^appleCycleMvAudioType$"))
async def apple_cycle_mv_audio_type(c: Client, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True): return
    try:
        opts = ["atmos", "ac3", "aac"]
        from .config_yaml import _read_yaml_lines, _get_key
        lines = _read_yaml_lines(Config.APPLE_CONFIG_YAML_PATH)
        cur = (_get_key(lines, 'mv-audio-type') or 'atmos').strip('"')
        try:
            idx = opts.index(cur)
        except Exception:
            idx = -1
        _yaml_set('mv-audio-type', opts[(idx + 1) % len(opts)])
    except Exception:
        pass
    await apple_cb(c, cb)


@Client.on_callback_query(filters.regex(pattern=r"^appleCycleMvMax$"))
async def apple_cycle_mv_max(c: Client, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True): return
    try:
        opts = ["1080", "1440", "2160"]
        from .config_yaml import _read_yaml_lines, _get_key
        lines = _read_yaml_lines(Config.APPLE_CONFIG_YAML_PATH)
        cur = (_get_key(lines, 'mv-max') or '2160').strip('"')
        try:
            idx = opts.index(cur)
        except Exception:
            idx = -1
        _yaml_set('mv-max', opts[(idx + 1) % len(opts)])
    except Exception:
        pass
    await apple_cb(c, cb)


@Client.on_callback_query(filters.regex(pattern=r"^appleToggleDlAlbumCoverPlaylist$"))
async def apple_toggle_dl_albumcover_playlist(c: Client, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True): return
    try:
        _yaml_toggle_bool('dl-albumcover-for-playlist', False)
    except Exception:
        pass
    await apple_cb(c, cb)


@Client.on_callback_query(filters.regex(pattern=r"^appleToggleUseSonginfoPlaylist$"))
async def apple_toggle_use_songinfo_playlist(c: Client, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True): return
    try:
        _yaml_toggle_bool('use-songinfo-for-playlist', False)
    except Exception:
        pass
    await apple_cb(c, cb)


@Client.on_callback_query(filters.regex(pattern=r"^appleCycleLimitMax$"))
async def apple_cycle_limit_max(c: Client, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True): return
    try:
        opts = ["100", "150", "200", "300", "400"]
        from .config_yaml import _read_yaml_lines, _get_key
        lines = _read_yaml_lines(Config.APPLE_CONFIG_YAML_PATH)
        cur = (_get_key(lines, 'limit-max') or '200').strip('"')
        try:
            idx = opts.index(cur)
        except Exception:
            idx = -1
        _yaml_set('limit-max', opts[(idx + 1) % len(opts)])
    except Exception:
        pass
    await apple_cb(c, cb)


@Client.on_callback_query(filters.regex(pattern=r"^appleCycleAlbumFolderFormat$"))
async def apple_cycle_album_folder_format(c: Client, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True): return
    try:
        presets = [
            "{AlbumName}",
            "{ArtistName} - {AlbumName}",
            "{ReleaseYear} - {ArtistName} - {AlbumName}",
            "{ReleaseYear} - {AlbumName}",
        ]
        from .config_yaml import _read_yaml_lines, _get_key
        lines = _read_yaml_lines(Config.APPLE_CONFIG_YAML_PATH)
        cur = (_get_key(lines, 'album-folder-format') or '{AlbumName}').strip('"')
        try:
            idx = presets.index(cur)
        except Exception:
            idx = -1
        _yaml_set('album-folder-format', presets[(idx + 1) % len(presets)])
    except Exception:
        pass
    await apple_cb(c, cb)


@Client.on_callback_query(filters.regex(pattern=r"^appleCyclePlaylistFolderFormat$"))
async def apple_cycle_playlist_folder_format(c: Client, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True): return
    try:
        presets = [
            "{PlaylistName}",
            "{ArtistName} - {PlaylistName}",
            "{Quality} - {PlaylistName}",
        ]
        from .config_yaml import _read_yaml_lines, _get_key
        lines = _read_yaml_lines(Config.APPLE_CONFIG_YAML_PATH)
        cur = (_get_key(lines, 'playlist-folder-format') or '{PlaylistName}').strip('"')
        try:
            idx = presets.index(cur)
        except Exception:
            idx = -1
        _yaml_set('playlist-folder-format', presets[(idx + 1) % len(presets)])
    except Exception:
        pass
    await apple_cb(c, cb)


@Client.on_callback_query(filters.regex(pattern=r"^appleCycleSongFileFormat$"))
async def apple_cycle_song_file_format(c: Client, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True): return
    try:
        presets = [
            "{SongNumer}. {SongName}",
            "{TrackNumber}. {SongName}",
            "{TrackNumber}. {ArtistName} - {SongName}",
            "{SongName} [{Quality}]",
        ]
        from .config_yaml import _read_yaml_lines, _get_key
        lines = _read_yaml_lines(Config.APPLE_CONFIG_YAML_PATH)
        cur = (_get_key(lines, 'song-file-format') or '{SongNumer}. {SongName}').strip('"')
        try:
            idx = presets.index(cur)
        except Exception:
            idx = -1
        _yaml_set('song-file-format', presets[(idx + 1) % len(presets)])
    except Exception:
        pass
    await apple_cb(c, cb)


@Client.on_callback_query(filters.regex(pattern=r"^appleCycleAacType$"))
async def apple_cycle_aac_type(c: Client, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True): return
    try:
        opts = ["aac-lc", "aac", "aac-binaural", "aac-downmix"]
        from .config_yaml import _read_yaml_lines, _get_key
        lines = _read_yaml_lines(Config.APPLE_CONFIG_YAML_PATH)
        cur = (_get_key(lines, 'aac-type') or 'aac-lc').strip('"')
        try:
            idx = opts.index(cur)
        except Exception:
            idx = -1
        _yaml_set('aac-type', opts[(idx + 1) % len(opts)])
    except Exception:
        pass
    await apple_cb(c, cb)


@Client.on_callback_query(filters.regex(pattern=r"^appleCycleAlacMax$"))
async def apple_cycle_alac_max(c: Client, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True): return
    try:
        opts = ["44100", "48000", "96000", "192000"]
        from .config_yaml import _read_yaml_lines, _get_key
        lines = _read_yaml_lines(Config.APPLE_CONFIG_YAML_PATH)
        cur = (_get_key(lines, 'alac-max') or '192000').strip('"')
        try:
            idx = opts.index(cur)
        except Exception:
            idx = -1
        _yaml_set('alac-max', opts[(idx + 1) % len(opts)])
    except Exception:
        pass
    await apple_cb(c, cb)


@Client.on_callback_query(filters.regex(pattern=r"^appleCycleAtmosMax$"))
async def apple_cycle_atmos_max(c: Client, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True): return
    try:
        opts = ["2448", "2768"]
        from .config_yaml import _read_yaml_lines, _get_key
        lines = _read_yaml_lines(Config.APPLE_CONFIG_YAML_PATH)
        cur = (_get_key(lines, 'atmos-max') or '2768').strip('"')
        try:
            idx = opts.index(cur)
        except Exception:
            idx = -1
        _yaml_set('atmos-max', opts[(idx + 1) % len(opts)])
    except Exception:
        pass
    await apple_cb(c, cb)


@Client.on_callback_query(filters.regex(pattern=r"^appleCycleM3u8Mode$"))
async def apple_cycle_m3u8_mode(c: Client, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True): return
    try:
        opts = ["hires", "all"]
        from .config_yaml import _read_yaml_lines, _get_key
        lines = _read_yaml_lines(Config.APPLE_CONFIG_YAML_PATH)
        cur = (_get_key(lines, 'get-m3u8-mode') or 'hires').strip('"')
        try:
            idx = opts.index(cur)
        except Exception:
            idx = -1
        _yaml_set('get-m3u8-mode', opts[(idx + 1) % len(opts)])
    except Exception:
        pass
    await apple_cb(c, cb)


@Client.on_callback_query(filters.regex(pattern=r"^applePromptLanguage$"))
async def apple_prompt_language(c: Client, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True): return
    # For simplicity, rotate a small set; full free-text would require convo state
    try:
        opts = ["", "en", "hi", "tr", "jp"]
        from .config_yaml import _read_yaml_lines, _get_key
        lines = _read_yaml_lines(Config.APPLE_CONFIG_YAML_PATH)
        cur = (_get_key(lines, 'language') or '').strip('"')
        try:
            idx = opts.index(cur)
        except Exception:
            idx = -1
        _yaml_set('language', opts[(idx + 1) % len(opts)])
    except Exception:
        pass
    await apple_cb(c, cb)


@Client.on_callback_query(filters.regex(pattern=r"^applePromptStorefront$"))
async def apple_prompt_storefront(c: Client, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True): return
    try:
        opts = ["US", "IN", "TR", "JP", "CA"]
        from .config_yaml import _read_yaml_lines, _get_key
        lines = _read_yaml_lines(Config.APPLE_CONFIG_YAML_PATH)
        cur = (_get_key(lines, 'storefront') or 'US').strip('"')
        try:
            idx = opts.index(cur)
        except Exception:
            idx = -1
        _yaml_set('storefront', opts[(idx + 1) % len(opts)])
    except Exception:
        pass
    await apple_cb(c, cb)


# Apple Wrapper: Stop with confirmation
@Client.on_callback_query(filters.regex(pattern=r"^appleStop$"))
async def apple_wrapper_stop_cb(c: Client, cb: CallbackQuery):
    if await check_user(cb.from_user.id, restricted=True):
        # Ask for confirmation
        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Confirm Stop", callback_data="appleStopConfirm")],
            [InlineKeyboardButton("❌ Cancel", callback_data="appleP")]
        ])
        await edit_message(cb.message, "Are you sure you want to stop the Wrapper?", buttons)


@Client.on_callback_query(filters.regex(pattern=r"^appleStopConfirm$"))
async def apple_wrapper_stop_confirm_cb(c: Client, cb: CallbackQuery):
    if await check_user(cb.from_user.id, restricted=True):
        from config import Config as Cfg
        import asyncio
        await c.answer_callback_query(cb.id, "Stopping wrapper...", show_alert=False)
        try:
            proc = await asyncio.create_subprocess_exec(
                "/bin/bash", Cfg.APPLE_WRAPPER_STOP_PATH,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            out = stdout.decode(errors='ignore')
            err = stderr.decode(errors='ignore')
            text = "⏹️ Wrapper stop result:\n\n" + (out.strip() or err.strip() or "Done.")
        except Exception as e:
            text = f"❌ Failed to stop wrapper: {e}"
        await edit_message(cb.message, text, InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="appleP")]]))


# Apple Wrapper: Setup flow entry (asks for username then password)
@Client.on_callback_query(filters.regex(pattern=r"^appleSetup$"))
async def apple_wrapper_setup_cb(c: Client, cb: CallbackQuery):
    if await check_user(cb.from_user.id, restricted=True):
        # Explain flow
        await edit_message(cb.message, "We'll set up the Wrapper. Please send your Apple ID username.\n\nYou can cancel anytime by sending /cancel.", InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="appleP")]]))
        # Mark state for this user
        from ..helpers.state import conversation_state
        # Also clear any other pending flows for safety
        await conversation_state.clear(cb.from_user.id)
        await conversation_state.start(cb.from_user.id, "apple_setup_username", {"chat_id": cb.message.chat.id, "msg_id": cb.message.id})


@Client.on_callback_query(filters.regex(pattern=r"^appleImportFile$"))
async def apple_import_file_cb(c: Client, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True):
        return

    target_dir = "/root/amalac/"
    await conversation_state.clear(cb.from_user.id)
    await conversation_state.start(cb.from_user.id, "awaiting_apple_music_file", {"target_dir": target_dir})
    await edit_message(
        cb.message,
        f"Please upload the file you want to import into `{target_dir}`.\nIt will overwrite any existing file with the same name. You can /cancel anytime.",
        InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Cancel", callback_data="appleP")]
        ])
    )


#----------------
# QOBUZ
#----------------
@Client.on_callback_query(filters.regex(pattern=r"^qbP"))
async def qobuz_cb(c, cb: CallbackQuery):
    if await check_user(cb.from_user.id, restricted=True):
        quality = {5: 'MP3 320', 6: 'Lossless', 7: '24B<=96KHZ', 27: '24B>96KHZ'}
        current = bot_set.qobuz.quality
        quality[current] = quality[current] + '✅'
        try:
            await edit_message(
                cb.message,
                lang.s.QOBUZ_QUALITY_PANEL,
                markup=qb_button(quality)
            )
        except:
            pass


@Client.on_callback_query(filters.regex(pattern=r"^qbQ"))
async def qobuz_quality_cb(c, cb: CallbackQuery):
    if await check_user(cb.from_user.id, restricted=True):
        qobuz = {5: 'MP3 320', 6: 'Lossless', 7: '24B<=96KHZ', 27: '24B>96KHZ'}
        to_set = cb.data.split('_')[1]
        bot_set.qobuz.quality = list(filter(lambda x: qobuz[x] == to_set, qobuz))[0]
        set_db.set_variable('QOBUZ_QUALITY', bot_set.qobuz.quality)
        await qobuz_cb(c, cb)


#----------------
# TIDAL
#----------------
@Client.on_callback_query(filters.regex(pattern=r"^tdP"))
async def tidal_cb(c, cb: CallbackQuery):
    if await check_user(cb.from_user.id, restricted=True):
        await edit_message(
            cb.message,
            lang.s.TIDAL_PANEL,
            tidal_buttons()  # auth and quality button (quality button only if auth already done)
        )


@Client.on_callback_query(filters.regex(pattern=r"^toggleLegacyTidal"))
async def toggle_legacy_tidal_cb(c, cb: CallbackQuery):
    if await check_user(cb.from_user.id, restricted=True):
        bot_set.tidal_legacy_enabled = not bot_set.tidal_legacy_enabled
        status = "ON" if bot_set.tidal_legacy_enabled else "OFF"
        await c.answer_callback_query(
            cb.id,
            f"Legacy Tidal is now {status}",
            show_alert=False
        )
        # Directly edit the message to refresh the buttons
        await edit_message(
            cb.message,
            lang.s.TIDAL_PANEL,
            tidal_buttons()
        )


@Client.on_callback_query(filters.regex(pattern=r"^tdQ"))
async def tidal_quality_cb(c, cb: CallbackQuery):
    if await check_user(cb.from_user.id, restricted=True):
        qualities = {
            'LOW': 'LOW',
            'HIGH': 'HIGH',
            'LOSSLESS': 'LOSSLESS'
        }
        if tidalapi.mobile_hires:
            qualities['HI_RES'] = 'MAX'
        qualities[tidalapi.quality] += '✅'

        await edit_message(
            cb.message,
            lang.s.TIDAL_PANEL,
            tidal_quality_button(qualities)
        )


@Client.on_callback_query(filters.regex(pattern=r"^tdSQ"))
async def tidal_set_quality_cb(c, cb: CallbackQuery):
    if await check_user(cb.from_user.id, restricted=True):
        to_set = cb.data.split('_')[1]

        if to_set == 'spatial':
            # options = ['OFF', 'ATMOS AC3 JOC', 'ATMOS AC4', 'Sony 360RA']
            # assuming atleast tv session is added
            options = ['OFF', 'ATMOS AC3 JOC']
            if tidalapi.mobile_atmos:
                options.append('ATMOS AC4')
            if tidalapi.mobile_atmos or tidalapi.mobile_hires:
                options.append('Sony 360RA')

            try:
                current = options.index(tidalapi.spatial)
            except:
                current = 0

            nexti = (current + 1) % 4
            tidalapi.spatial = options[nexti]
            set_db.set_variable('TIDAL_SPATIAL', options[nexti])
        else:
            qualities = {'LOW': 'LOW', 'HIGH': 'HIGH', 'LOSSLESS': 'LOSSLESS', 'HI_RES': 'MAX'}
            to_set = list(filter(lambda x: qualities[x] == to_set, qualities))[0]
            tidalapi.quality = to_set
            set_db.set_variable('TIDAL_QUALITY', to_set)

        await tidal_quality_cb(c, cb)


# show login button if not logged in
# show refresh button in case logged in exist (both tv and mobile)
@Client.on_callback_query(filters.regex(pattern=r"^tdAuth"))
async def tidal_auth_cb(c, cb: CallbackQuery):
    if await check_user(cb.from_user.id, restricted=True):
        sub = tidalapi.sub_type
        hires = True if tidalapi.mobile_hires else False
        atmos = True if tidalapi.mobile_atmos else False
        tv = True if tidalapi.tv_session else False

        await edit_message(
            cb.message,
            lang.s.TIDAL_AUTH_PANEL.format(sub, hires, atmos, tv),
            tidal_auth_buttons()
        )


@Client.on_callback_query(filters.regex(pattern=r"^tdLogin"))
async def tidal_login_cb(c: Client, cb: CallbackQuery):
    if await check_user(cb.from_user.id, restricted=True):
        auth_url, err = await tidalapi.get_tv_login_url()
        if err:
            return await c.answer_callback_query(
                cb.id,
                err,
                True
            )

        await edit_message(
            cb.message,
            lang.s.TIDAL_AUTH_URL.format(auth_url),
            tidal_auth_buttons()
        )

        sub, err = await tidalapi.login_tv()
        if err:
            return await edit_message(
                cb.message,
                lang.s.ERR_LOGIN_TIDAL_TV_FAILED.format(err),
                tidal_auth_buttons()
            )
        if sub:
            bot_set.tidal = tidalapi
            bot_set.clients.append(tidalapi)

            await bot_set.save_tidal_login(tidalapi.tv_session)

            hires = True if tidalapi.mobile_hires else False
            atmos = True if tidalapi.mobile_atmos else False
            tv = True if tidalapi.tv_session else False
            await edit_message(
                cb.message,
                lang.s.TIDAL_AUTH_PANEL.format(sub, hires, atmos, tv) + '\n' + lang.s.TIDAL_AUTH_SUCCESSFULL,
                tidal_auth_buttons()
            )


@Client.on_callback_query(filters.regex(pattern=r"^tdRemove"))
async def tidal_remove_login_cb(c: Client, cb: CallbackQuery):
    if await check_user(cb.from_user.id, restricted=True):
        set_db.set_variable("TIDAL_AUTH_DATA", 0, True, None)

        tidalapi.tv_session = None
        tidalapi.mobile_atmos = None
        tidalapi.mobile_hires = None
        tidalapi.sub_type = None
        tidalapi.saved = []

        await tidalapi.session.close()
        bot_set.tidal = None

        await c.answer_callback_query(
            cb.id,
            lang.s.TIDAL_REMOVED_SESSION,
            True
        )

        await tidal_auth_cb(c, cb)


#--------------------
# TIDAL DL NG
#--------------------
@Client.on_callback_query(filters.regex(pattern=r"^tidalNgP"))
async def tidal_ng_cb(c, cb: CallbackQuery):
    if await check_user(cb.from_user.id, restricted=True):
        text = (
            "**Tidal NG Settings**\n\n"
            "Configuration for this provider is now handled via commands, "
            "similar to the Apple Music provider. This provides more reliable "
            "and real-time control over the `settings.json` file.\n\n"
            "**Available Commands:**\n"
            "🔹 `/tidal_ng_get <key>`\n"
            "🔹 `/tidal_ng_set <key> <value>`\n"
            "🔹 `/tidal_ng_toggle <key>`\n"
            "🔹 `/tidal_ng_show`\n\n"
            "Use `/tidal_ng_config` for more help.\n\n"
            "You can also use the buttons below for other actions."
        )
        # Inject Tidal NG specific zip toggles and advanced settings pulled from CLI
        from ..settings import bot_set as _bs
        try:
            from .tidal_ng_settings import _read_json, JSON_PATH, CHOICE_KEYS
            _cfg = _read_json(JSON_PATH)
        except Exception:
            _cfg = {}
            CHOICE_KEYS = {"quality_audio": ["LOW","HIGH","LOSSLESS","HI_RES_LOSSLESS"], "quality_video": ["360","480","720","1080"]}
        zip_album_label = f"Zip Albums (NG): {'ON ✅' if getattr(_bs, 'tidal_ng_album_zip', False) else 'OFF'}"
        zip_playlist_label = f"Zip Playlists (NG): {'ON ✅' if getattr(_bs, 'tidal_ng_playlist_zip', False) else 'OFF'}"
        # Advanced toggles/choices reflecting settings.json
        _qa = str(_cfg.get('quality_audio', 'HIGH'))
        _qv = str(_cfg.get('quality_video', '480'))
        qa_label = f"Audio Quality: {_qa}"
        qv_label = f"Video Quality: {_qv}"
        vd_label = f"Video Download: {'ON ✅' if bool(_cfg.get('video_download', True)) else 'OFF'}"
        xf_label = f"Extract FLAC: {'ON ✅' if bool(_cfg.get('extract_flac', True)) else 'OFF'}"
        mp4_label = f"Convert to MP4: {'ON ✅' if bool(_cfg.get('video_convert_mp4', True)) else 'OFF'}"
        se_label = f"Skip Existing: {'ON ✅' if bool(_cfg.get('skip_existing', True)) else 'OFF'}"
        st_label = f"Symlink to Track: {'ON ✅' if bool(_cfg.get('symlink_to_track', False)) else 'OFF'}"
        pc_label = f"Playlist Create: {'ON ✅' if bool(_cfg.get('playlist_create', False)) else 'OFF'}"
        dsp_min = float(_cfg.get('download_delay_sec_min', 3.0) or 3.0)
        dsp_max = float(_cfg.get('download_delay_sec_max', 5.0) or 5.0)
        delay_label = f"Delay: {dsp_min:.1f}/{dsp_max:.1f}s"
        sim_label = f"Sim per Track: {int(_cfg.get('downloads_simultaneous_per_track_max', 20) or 20)}"
        pad_label = f"Track Pad Min: {int(_cfg.get('album_track_num_pad_min', 1) or 1)}"
        le_label = f"Lyrics Embed: {'ON ✅' if bool(_cfg.get('lyrics_embed', False)) else 'OFF'}"
        lf_label = f"Lyrics File: {'ON ✅' if bool(_cfg.get('lyrics_file', False)) else 'OFF'}"
        rg_label = f"Replay Gain: {'ON ✅' if bool(_cfg.get('metadata_replay_gain', True)) else 'OFF'}"
        ce_label = f"Cover Embed: {'ON ✅' if bool(_cfg.get('metadata_cover_embed', True)) else 'OFF'}"
        caf_label = f"Cover File: {'ON ✅' if bool(_cfg.get('cover_album_file', True)) else 'OFF'}"

        # Top-level guard toggle for Tidal NG preset cycling
        try:
            from ..settings import bot_set as _bs_guard
            guard_label = f"Preset Buttons: {'ON ✅' if getattr(_bs_guard, 'tidal_ng_cycle_presets_enabled', True) else 'OFF'}"
            guard_enabled = getattr(_bs_guard, 'tidal_ng_cycle_presets_enabled', True)
        except Exception:
            guard_label = "Preset Buttons: ON ✅"
            guard_enabled = True

        buttons = [
            [InlineKeyboardButton(guard_label, callback_data="tidalNgTogglePresetGuard")],
            [
                InlineKeyboardButton("🔑 Login", callback_data="tidalNgLogin"),
                InlineKeyboardButton("🚨 Logout", callback_data="tidalNgLogout")
            ],
            [
                InlineKeyboardButton("📂 Import Config File", callback_data="tidalNg_importFile"),
                InlineKeyboardButton("⚙️ Execute cfg", callback_data="tidal_ng_execute_cfg")
            ],
            [
                InlineKeyboardButton("🗑️ Manage Files", callback_data="tidalNgManageFiles")
            ],
        ]

        if guard_enabled:
            buttons += [
                [
                    InlineKeyboardButton("↓ Concurrency -", callback_data="tidalNgDecConcurrency"),
                    InlineKeyboardButton("↑ Concurrency +", callback_data="tidalNgIncConcurrency")
                ],
            ]
        
        if guard_enabled:
            buttons += [
                [
                    InlineKeyboardButton(qa_label, callback_data="tidalNgCycleQualityAudio"),
                    InlineKeyboardButton(qv_label, callback_data="tidalNgCycleQualityVideo"),
                ],
                [
                    InlineKeyboardButton(vd_label, callback_data="tidalNgToggleVideoDownload"),
                    InlineKeyboardButton(xf_label, callback_data="tidalNgToggleExtractFlac"),
                ],
                [
                    InlineKeyboardButton(mp4_label, callback_data="tidalNgToggleConvertMp4"),
                    InlineKeyboardButton(se_label, callback_data="tidalNgToggleSkipExisting"),
                ],
                [
                    InlineKeyboardButton(st_label, callback_data="tidalNgToggleSymlink"),
                    InlineKeyboardButton(pc_label, callback_data="tidalNgTogglePlaylistCreate"),
                ],
                [
                    InlineKeyboardButton(delay_label, callback_data="tidalNgCycleDelay"),
                    InlineKeyboardButton(sim_label, callback_data="tidalNgCycleSimPerTrack"),
                ],
                [
                    InlineKeyboardButton(pad_label, callback_data="tidalNgCycleTrackPad"),
                    InlineKeyboardButton("Reset Delays", callback_data="tidalNgResetDelay"),
                ],
                [
                    InlineKeyboardButton(le_label, callback_data="tidalNgToggleLyricsEmbed"),
                    InlineKeyboardButton(lf_label, callback_data="tidalNgToggleLyricsFile"),
                ],
                [
                    InlineKeyboardButton(rg_label, callback_data="tidalNgToggleReplayGain"),
                    InlineKeyboardButton(ce_label, callback_data="tidalNgToggleCoverEmbed"),
                ],
                [
                    InlineKeyboardButton(caf_label, callback_data="tidalNgToggleCoverFile"),
                ],
                [
                    InlineKeyboardButton(zip_album_label, callback_data="tidalNgToggleZipAlbum"),
                    InlineKeyboardButton(zip_playlist_label, callback_data="tidalNgToggleZipPlaylist")
                ],
            ]
        buttons.append([InlineKeyboardButton("🔙 Back", callback_data="providerPanel")])
        await edit_message(
            cb.message,
            text,
            InlineKeyboardMarkup(buttons)
        )

@Client.on_callback_query(filters.regex(pattern=r"^tidal_ng_execute_cfg$"))
async def tidal_ng_execute_cfg_cb(c, cb: CallbackQuery):
    if await check_user(cb.from_user.id, restricted=True):
        from bot.helpers.tidal_ng.handler import TIDAL_DL_NG_CLI_PATH
        msg = await edit_message(cb.message, "⚙️ Executing `tidal-dl-ng cfg`...")

        try:
            process = await asyncio.create_subprocess_exec(
                "python", TIDAL_DL_NG_CLI_PATH, "cfg",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()

            output = stdout.decode().strip()
            error = stderr.decode().strip()

            response_text = ""
            if output:
                response_text += f"**Output:**\n```{output}```\n\n"
            if error:
                response_text += f"**Errors:**\n```{error}```"

            if not response_text:
                response_text = "Command executed with no output."

            back_button = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="tidalNgP")]])
            await edit_message(msg, response_text, back_button)

        except Exception as e:
            back_button = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="tidalNgP")]])
            await edit_message(msg, f"❌ **An Error Occurred:**\n`{str(e)}`", back_button)


@Client.on_callback_query(filters.regex(pattern=r"^tidalNg_importFile$"))
async def tidal_ng_import_file_cb(c, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True):
        return

    buttons = [
        [InlineKeyboardButton("main config (`tidal_dl_ng`)", callback_data="tidalNg_setImportDir|main")],
        [InlineKeyboardButton("dev config (`tidal_dl_ng-dev`)", callback_data="tidalNg_setImportDir|dev")],
        [InlineKeyboardButton("🔙 Back", callback_data="tidalNgP")]
    ]
    await edit_message(
        cb.message,
        "Please choose the destination directory for your configuration file.",
        InlineKeyboardMarkup(buttons)
    )

@Client.on_callback_query(filters.regex(pattern=r"^tidalNg_setImportDir\|"))
async def tidal_ng_set_import_dir_cb(c, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True):
        return

    choice = cb.data.split("|")[1]
    if choice == "main":
        target_dir = "/root/.config/tidal_dl_ng/"
    else:
        target_dir = "/root/.config/tidal_dl_ng-dev/"

    if not os.path.exists(target_dir):
        await edit_message(
            cb.message,
            f"The destination directory (`{target_dir}`) does not exist. Shall I create it for you?",
            InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Yes, create it", callback_data=f"tidalNg_createDir|{choice}")],
                [InlineKeyboardButton("❌ Cancel", callback_data="tidalNgP")]
            ])
        )
    else:
        await conversation_state.clear(cb.from_user.id)
        await conversation_state.start(cb.from_user.id, "awaiting_tidal_ng_file", {"target_dir": target_dir})
        await edit_message(
            cb.message,
            "Please upload the file you want to import. You can /cancel anytime.",
            InlineKeyboardMarkup([
                [InlineKeyboardButton("❌ Cancel", callback_data="tidalNgP")]
            ])
        )

@Client.on_callback_query(filters.regex(pattern=r"^tidalNg_createDir\|"))
async def tidal_ng_create_dir_cb(c, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True):
        return

    choice = cb.data.split("|")[1]
    if choice == "main":
        target_dir = "/root/.config/tidal_dl_ng/"
    else:
        target_dir = "/root/.config/tidal_dl_ng-dev/"

    try:
        os.makedirs(target_dir, mode=0o777, exist_ok=True)
        await cb.answer("Directory created successfully!", show_alert=False)
        # Now ask for the file
        await conversation_state.clear(cb.from_user.id)
        await conversation_state.start(cb.from_user.id, "awaiting_tidal_ng_file", {"target_dir": target_dir})
        await edit_message(
            cb.message,
            "Please upload the file you want to import. You can /cancel anytime.",
            InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="tidalNgP")]])
        )
    except Exception as e:
        await edit_message(
            cb.message,
            f"❌ **Failed to create directory:**\n`{str(e)}`",
            InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="tidalNgP")]])
        )

@Client.on_callback_query(filters.regex(pattern=r"^tidalNgLogin"))
async def tidal_ng_login_cb(c, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True):
        return

    msg = await edit_message(
        cb.message,
        "⏳ **Attempting to log in to Tidal DL NG...**\n\n"
        "Please wait while the bot starts the login process."
    )

    try:
        command = "env PYTHONPATH=/usr/src/app/tidal-dl-ng python cli.py login"
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd='/usr/src/app/tidal-dl-ng/tidal_dl_ng'
        )

        # Timeout for the entire login process
        try:
            # We will read stdout line by line
            url_found = False
            while True:
                line = await asyncio.wait_for(process.stdout.readline(), timeout=305.0)
                if not line:
                    break

                output = line.decode().strip()
                if "https://link.tidal.com/" in output:
                    url_found = True
                    await edit_message(
                        msg,
                        f"🔗 **Login URL Detected**\n\n"
                        f"Please visit the following URL to log in. The code will expire in 5 minutes.\n\n"
                        f"`{output}`\n\n"
                        f"The bot is waiting for you to complete the login...",
                    )

                if "The login was successful" in output:
                    await edit_message(
                        msg,
                        f"✅ **Login Successful!**\n\n"
                        f"Your Tidal DL NG credentials have been stored."
                    )
                    await process.wait() # ensure process is finished
                    return

            # If loop breaks and we haven't returned, something went wrong
            stderr_output = await process.stderr.read()
            err_msg = stderr_output.decode().strip()
            await edit_message(
                msg,
                f"❌ **Login Failed**\n\n"
                f"The login process failed. Please try again.\n\n"
                f"**Error:**\n`{err_msg or 'No error message from script.'}`"
            )

        except asyncio.TimeoutError:
            process.kill()
            await edit_message(
                msg,
                "❌ **Login Timed Out**\n\n"
                "You did not complete the login within 5 minutes. Please try again."
            )

    except Exception as e:
        await edit_message(
            msg,
            f"❌ **An Error Occurred**\n\n"
            f"An unexpected error occurred while trying to log in.\n\n"
            f"`{str(e)}`"
        )


@Client.on_callback_query(filters.regex(pattern=r"^tidalNgLogout"))
async def tidal_ng_logout_cb(c, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True):
        return

    msg = await edit_message(
        cb.message,
        "⏳ **Attempting to log out from Tidal DL NG...**"
    )

    try:
        command = "env PYTHONPATH=/usr/src/app/tidal-dl-ng python cli.py logout"
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd='/usr/src/app/tidal-dl-ng/tidal_dl_ng'
        )

        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=60.0)

        output = stdout.decode().strip()
        err_msg = stderr.decode().strip()

        if process.returncode == 0 and "successfully logged out" in output:
            await edit_message(
                msg,
                "✅ **Logout Successful!**\n\n"
                "You have been logged out from Tidal DL NG."
            )
        else:
            await edit_message(
                msg,
                f"❌ **Logout Failed**\n\n"
                f"The logout process failed. Please try again.\n\n"
                f"**Error:**\n`{err_msg or output or 'No error message from script.'}`"
            )

    except asyncio.TimeoutError:
        process.kill()
        await edit_message(
            msg,
            "❌ **Logout Timed Out**\n\nPlease try again."
        )
    except Exception as e:
        await edit_message(
            msg,
            f"❌ **An Error Occurred**\n\n"
            f"An unexpected error occurred while trying to log out.\n\n"
            f"`{str(e)}`"
        )


@Client.on_callback_query(filters.regex(pattern=r"^tidalNgManageFiles$"))
async def tidal_ng_manage_files_cb(c: Client, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True):
        return

    config_dirs = ["/root/.config/tidal_dl_ng/", "/root/.config/tidal_dl_ng-dev/"]
    all_files = []
    for directory in config_dirs:
        if os.path.isdir(directory):
            try:
                for filename in os.listdir(directory):
                    filepath = os.path.join(directory, filename)
                    if os.path.isfile(filepath):
                        all_files.append(filepath)
            except OSError:
                pass

    buttons = []
    text = "Found the following configuration files.\nSelect a file to delete:"

    if not all_files:
        text = "No configuration files found."
    else:
        for f_path in all_files:
            # Use a short prefix and a safe separator to stay within callback data limits
            callback_data = f"tnfa:{f_path}"
            parent_dir = os.path.basename(os.path.dirname(f_path))
            file_name_display = f"{parent_dir}/{os.path.basename(f_path)}"
            buttons.append([InlineKeyboardButton(f"📄 {file_name_display}", callback_data=callback_data)])

    buttons.append([InlineKeyboardButton("🔙 Back", callback_data="tidalNgP")])

    await edit_message(
        cb.message,
        text,
        InlineKeyboardMarkup(buttons)
    )


@Client.on_callback_query(filters.regex(pattern=r"^tnfa:"))
async def tidal_ng_file_action_cb(c: Client, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True):
        return

    try:
        filepath = cb.data.split(":", 1)[1]
    except IndexError:
        await cb.answer("Error: Invalid file path in callback.", show_alert=True)
        return

    filename = os.path.basename(filepath)
    text = f"Choose an action for file:\n`{filename}`"

    buttons = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⬇️ Download", callback_data=f"tndl:{filepath}"),
            InlineKeyboardButton("❌ Delete", callback_data=f"tndc:{filepath}")
        ],
        [
            InlineKeyboardButton("🔙 Back", callback_data="tidalNgManageFiles")
        ]
    ])

    await edit_message(cb.message, text, buttons)


@Client.on_callback_query(filters.regex(pattern=r"^tndc:"))
async def tidal_ng_delete_confirm_cb(c: Client, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True):
        return

    try:
        filepath = cb.data.split(":", 1)[1]
    except IndexError:
        await cb.answer("Error: Invalid file path in callback.", show_alert=True)
        return

    filename = os.path.basename(filepath)
    text = f"Are you sure you want to delete the file `{filename}`?\n\n**This action cannot be undone.**"

    buttons = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Confirm Delete", callback_data=f"tndd:{filepath}"),
            InlineKeyboardButton("❌ Cancel", callback_data="tidalNgManageFiles")
        ]
    ])

    await edit_message(cb.message, text, buttons)


@Client.on_callback_query(filters.regex(pattern=r"^tndd:"))
async def tidal_ng_delete_do_cb(c: Client, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True):
        return

    try:
        filepath = cb.data.split(":", 1)[1]
    except IndexError:
        await cb.answer("Error: Invalid file path in callback.", show_alert=True)
        return

    try:
        if os.path.isfile(filepath):
            os.remove(filepath)
            await cb.answer("File deleted successfully.", show_alert=False)
        else:
            await cb.answer("File not found.", show_alert=True)
    except Exception as e:
        await cb.answer(f"Error: {e}", show_alert=True)

    # Refresh the file list
    await tidal_ng_manage_files_cb(c, cb)


@Client.on_callback_query(filters.regex(pattern=r"^tndl:"))
async def tidal_ng_download_file_cb(c: Client, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True):
        return

    await cb.answer("Preparing your file...")
    try:
        filepath = cb.data.split(":", 1)[1]
        if os.path.isfile(filepath):
            await c.send_document(
                chat_id=cb.message.chat.id,
                document=filepath
            )
        else:
            await c.send_message(cb.message.chat.id, "Error: File not found.")
    except Exception as e:
        await c.send_message(cb.message.chat.id, f"An error occurred while sending the file: {e}")


@Client.on_callback_query(filters.regex(pattern=r"^tidalNgToggleZipAlbum$"))
async def tidal_ng_toggle_zip_album(c, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True):
        return
    try:
        from ..settings import bot_set
        from ..helpers.database.pg_impl import set_db
        bot_set.tidal_ng_album_zip = not bool(getattr(bot_set, 'tidal_ng_album_zip', False))
        set_db.set_variable('TIDAL_NG_ALBUM_ZIP', bot_set.tidal_ng_album_zip)
    except Exception:
        pass
    await tidal_ng_cb(c, cb)


@Client.on_callback_query(filters.regex(pattern=r"^tidalNgToggleZipPlaylist$"))
async def tidal_ng_toggle_zip_playlist(c, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True):
        return
    try:
        from ..settings import bot_set
        from ..helpers.database.pg_impl import set_db
        bot_set.tidal_ng_playlist_zip = not bool(getattr(bot_set, 'tidal_ng_playlist_zip', False))
        set_db.set_variable('TIDAL_NG_PLAYLIST_ZIP', bot_set.tidal_ng_playlist_zip)
    except Exception:
        pass
    await tidal_ng_cb(c, cb)
@Client.on_callback_query(filters.regex(pattern=r"^tidalNgTogglePresetGuard$"))
async def tidal_ng_toggle_preset_guard(c, cb: CallbackQuery):
    if await check_user(cb.from_user.id, restricted=True):
        try:
            from ..settings import bot_set
            from ..helpers.database.pg_impl import set_db
            bot_set.tidal_ng_cycle_presets_enabled = not bool(getattr(bot_set, 'tidal_ng_cycle_presets_enabled', True))
            set_db.set_variable('TIDAL_NG_CYCLE_PRESETS_ENABLED', bot_set.tidal_ng_cycle_presets_enabled)
        except Exception:
            pass
        await tidal_ng_cb(c, cb)


@Client.on_callback_query(filters.regex(pattern=r"^tidalNgIncConcurrency$"))
async def tidal_ng_inc_concurrency(c, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True):
        return
    from .tidal_ng_settings import _mutate_json_key
    ok, msg = _mutate_json_key(
        "downloads_concurrent_max",
        lambda prev: max(1, int(prev or 3) + 1)
    )
    await tidal_ng_cb(c, cb)


@Client.on_callback_query(filters.regex(pattern=r"^tidalNgDecConcurrency$"))
async def tidal_ng_dec_concurrency(c, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True):
        return
    from .tidal_ng_settings import _mutate_json_key
    ok, msg = _mutate_json_key(
        "downloads_concurrent_max",
        lambda prev: max(1, int(prev or 3) - 1)
    )
    await tidal_ng_cb(c, cb)


@Client.on_callback_query(filters.regex(pattern=r"^tidalNgCycleQualityAudio$"))
async def tidal_ng_cycle_quality_audio(c, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True):
        return
    try:
        from .tidal_ng_settings import _read_json, _write_json, _backup, JSON_PATH, CHOICE_KEYS
        data = _read_json(JSON_PATH)
        choices = CHOICE_KEYS.get('quality_audio') or ["LOW","HIGH","LOSSLESS","HI_RES_LOSSLESS"]
        cur = str(data.get('quality_audio', 'HIGH'))
        try:
            idx = choices.index(cur)
        except Exception:
            idx = -1
        newv = choices[(idx + 1) % len(choices)]
        _backup(JSON_PATH)
        data['quality_audio'] = newv
        _write_json(JSON_PATH, data)
    except Exception:
        pass
    await tidal_ng_cb(c, cb)


@Client.on_callback_query(filters.regex(pattern=r"^tidalNgCycleQualityVideo$"))
async def tidal_ng_cycle_quality_video(c, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True):
        return
    try:
        from .tidal_ng_settings import _read_json, _write_json, _backup, JSON_PATH, CHOICE_KEYS
        data = _read_json(JSON_PATH)
        choices = CHOICE_KEYS.get('quality_video') or ["360","480","720","1080"]
        cur = str(data.get('quality_video', '480'))
        try:
            idx = choices.index(cur)
        except Exception:
            idx = -1
        newv = choices[(idx + 1) % len(choices)]
        _backup(JSON_PATH)
        data['quality_video'] = newv
        _write_json(JSON_PATH, data)
    except Exception:
        pass
    await tidal_ng_cb(c, cb)


@Client.on_callback_query(filters.regex(pattern=r"^tidalNgToggleVideoDownload$"))
async def tidal_ng_toggle_video_download(c, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True):
        return
    try:
        from .tidal_ng_settings import _read_json, _write_json, _backup, JSON_PATH
        data = _read_json(JSON_PATH)
        cur = bool(data.get('video_download', True))
        data['video_download'] = (not cur)
        _backup(JSON_PATH)
        _write_json(JSON_PATH, data)
    except Exception:
        pass
    await tidal_ng_cb(c, cb)


@Client.on_callback_query(filters.regex(pattern=r"^tidalNgToggleExtractFlac$"))
async def tidal_ng_toggle_extract_flac(c, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True):
        return
    try:
        from .tidal_ng_settings import _read_json, _write_json, _backup, JSON_PATH
        data = _read_json(JSON_PATH)
        cur = bool(data.get('extract_flac', True))
        data['extract_flac'] = (not cur)
        _backup(JSON_PATH)
        _write_json(JSON_PATH, data)
    except Exception:
        pass
    await tidal_ng_cb(c, cb)


def _toggle_json_bool(key: str):
    from .tidal_ng_settings import _read_json, _write_json, _backup, JSON_PATH
    data = _read_json(JSON_PATH)
    cur = bool(data.get(key, False))
    data[key] = (not cur)
    _backup(JSON_PATH)
    _write_json(JSON_PATH, data)


@Client.on_callback_query(filters.regex(pattern=r"^tidalNgToggleLyricsEmbed$"))
async def tidal_ng_toggle_lyrics_embed(c, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True): return
    try:
        _toggle_json_bool('lyrics_embed')
    except Exception:
        pass
    await tidal_ng_cb(c, cb)


@Client.on_callback_query(filters.regex(pattern=r"^tidalNgToggleLyricsFile$"))
async def tidal_ng_toggle_lyrics_file(c, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True): return
    try:
        _toggle_json_bool('lyrics_file')
    except Exception:
        pass
    await tidal_ng_cb(c, cb)


@Client.on_callback_query(filters.regex(pattern=r"^tidalNgToggleReplayGain$"))
async def tidal_ng_toggle_replay_gain(c, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True): return
    try:
        _toggle_json_bool('metadata_replay_gain')
    except Exception:
        pass
    await tidal_ng_cb(c, cb)


@Client.on_callback_query(filters.regex(pattern=r"^tidalNgToggleCoverEmbed$"))
async def tidal_ng_toggle_cover_embed(c, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True): return
    try:
        _toggle_json_bool('metadata_cover_embed')
    except Exception:
        pass
    await tidal_ng_cb(c, cb)


@Client.on_callback_query(filters.regex(pattern=r"^tidalNgToggleCoverFile$"))
async def tidal_ng_toggle_cover_file(c, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True): return
    try:
        _toggle_json_bool('cover_album_file')
    except Exception:
        pass
    await tidal_ng_cb(c, cb)


@Client.on_callback_query(filters.regex(pattern=r"^tidalNgInteractive$"))
async def tidal_ng_interactive_menu(c, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True): return
    rows = [
        [InlineKeyboardButton("Set quality_audio", callback_data="tidalNgPromptJson|quality_audio")],
        [InlineKeyboardButton("Set quality_video", callback_data="tidalNgPromptJson|quality_video")],
        [InlineKeyboardButton("Set download_base_path", callback_data="tidalNgPromptJson|download_base_path")],
        [InlineKeyboardButton("Set downloads_concurrent_max", callback_data="tidalNgPromptJson|downloads_concurrent_max")],
        [InlineKeyboardButton("Set metadata_cover_dimension", callback_data="tidalNgPromptJson|metadata_cover_dimension")],
        [InlineKeyboardButton("🔙 Back", callback_data="tidalNgP")],
    ]
    await edit_message(cb.message, "Send a value for the selected Tidal NG key.", InlineKeyboardMarkup(rows))


@Client.on_callback_query(filters.regex(pattern=r"^tidalNgPromptJson\|"))
async def tidal_ng_prompt_json(c, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True): return
    try:
        key = cb.data.split("|", 1)[1]
    except Exception:
        key = None
    if not key:
        return await tidal_ng_interactive_menu(c, cb)
    await conversation_state.start(cb.from_user.id, "tidal_ng_json_set", {"key": key, "chat_id": cb.message.chat.id})
    await edit_message(cb.message, f"Please send a value for <code>{key}</code>.\nYou can /cancel to abort.", InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="tidalNgP")]]))


@Client.on_message(filters.text, group=14)
async def tidal_ng_handle_json_value(c: Client, msg: Message):
    from ..helpers.state import conversation_state as cs
    st = await cs.get(msg.from_user.id)
    if not st or st.get("stage") != "tidal_ng_json_set":
        return
    key = (st.get("data") or {}).get("key")
    if not key:
        await cs.clear(msg.from_user.id)
        return
    val = (msg.text or "").strip()
    try:
        from .tidal_ng_settings import _read_json, _write_json, _backup, JSON_PATH
        data = _read_json(JSON_PATH)
        _backup(JSON_PATH)
        # Cast numeric keys when appropriate
        if key in {"downloads_concurrent_max", "metadata_cover_dimension"}:
            try:
                data[key] = int(val)
            except Exception:
                data[key] = val
        else:
            data[key] = val
        _write_json(JSON_PATH, data)
        await send_message(msg, f"✅ Set <code>{key}</code>.")
    except Exception as e:
        await send_message(msg, f"❌ Failed to set <code>{key}</code>: {e}")
    await cs.clear(msg.from_user.id)


@Client.on_callback_query(filters.regex(pattern=r"^tidalNgToggleConvertMp4$"))
async def tidal_ng_toggle_convert_mp4(c, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True): return
    try:
        _toggle_json_bool('video_convert_mp4')
    except Exception:
        pass
    await tidal_ng_cb(c, cb)


@Client.on_callback_query(filters.regex(pattern=r"^tidalNgToggleSkipExisting$"))
async def tidal_ng_toggle_skip_existing(c, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True): return
    try:
        _toggle_json_bool('skip_existing')
    except Exception:
        pass
    await tidal_ng_cb(c, cb)


@Client.on_callback_query(filters.regex(pattern=r"^tidalNgToggleSymlink$"))
async def tidal_ng_toggle_symlink(c, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True): return
    try:
        _toggle_json_bool('symlink_to_track')
    except Exception:
        pass
    await tidal_ng_cb(c, cb)


@Client.on_callback_query(filters.regex(pattern=r"^tidalNgTogglePlaylistCreate$"))
async def tidal_ng_toggle_playlist_create(c, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True): return
    try:
        _toggle_json_bool('playlist_create')
    except Exception:
        pass
    await tidal_ng_cb(c, cb)


@Client.on_callback_query(filters.regex(pattern=r"^tidalNgCycleDelay$"))
async def tidal_ng_cycle_delay(c, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True): return
    try:
        from .tidal_ng_settings import _read_json, _write_json, _backup, JSON_PATH
        data = _read_json(JSON_PATH)
        presets = [(1.0, 2.0), (3.0, 5.0), (5.0, 10.0), (0.0, 0.0)]
        cur = (float(data.get('download_delay_sec_min', 3.0) or 3.0), float(data.get('download_delay_sec_max', 5.0) or 5.0))
        try:
            idx = presets.index(cur)
        except Exception:
            idx = -1
        newv = presets[(idx + 1) % len(presets)]
        _backup(JSON_PATH)
        data['download_delay'] = (newv != (0.0, 0.0))
        data['download_delay_sec_min'] = newv[0]
        data['download_delay_sec_max'] = newv[1]
        _write_json(JSON_PATH, data)
    except Exception:
        pass
    await tidal_ng_cb(c, cb)


@Client.on_callback_query(filters.regex(pattern=r"^tidalNgResetDelay$"))
async def tidal_ng_reset_delay(c, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True): return
    try:
        from .tidal_ng_settings import _read_json, _write_json, _backup, JSON_PATH
        data = _read_json(JSON_PATH)
        _backup(JSON_PATH)
        data['download_delay'] = True
        data['download_delay_sec_min'] = 3.0
        data['download_delay_sec_max'] = 5.0
        _write_json(JSON_PATH, data)
    except Exception:
        pass
    await tidal_ng_cb(c, cb)


@Client.on_callback_query(filters.regex(pattern=r"^tidalNgCycleSimPerTrack$"))
async def tidal_ng_cycle_sim_per_track(c, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True): return
    try:
        from .tidal_ng_settings import _read_json, _write_json, _backup, JSON_PATH
        data = _read_json(JSON_PATH)
        options = [8, 12, 16, 20, 24]
        cur = int(data.get('downloads_simultaneous_per_track_max', 20) or 20)
        try:
            idx = options.index(cur)
        except Exception:
            idx = -1
        newv = options[(idx + 1) % len(options)]
        _backup(JSON_PATH)
        data['downloads_simultaneous_per_track_max'] = newv
        _write_json(JSON_PATH, data)
    except Exception:
        pass
    await tidal_ng_cb(c, cb)


@Client.on_callback_query(filters.regex(pattern=r"^tidalNgCycleTrackPad$"))
async def tidal_ng_cycle_track_pad(c, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True): return
    try:
        from .tidal_ng_settings import _read_json, _write_json, _backup, JSON_PATH
        data = _read_json(JSON_PATH)
        options = [1, 2, 3]
        cur = int(data.get('album_track_num_pad_min', 1) or 1)
        try:
            idx = options.index(cur)
        except Exception:
            idx = -1
        newv = options[(idx + 1) % len(options)]
        _backup(JSON_PATH)
        data['album_track_num_pad_min'] = newv
        _write_json(JSON_PATH, data)
    except Exception:
        pass
    await tidal_ng_cb(c, cb)
