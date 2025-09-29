import bot.helpers.translations as lang
from bot.settings import bot_set
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from config import Config
import os

main_button = [[InlineKeyboardButton(text=lang.s.MAIN_MENU_BUTTON, callback_data="main_menu")]]
close_button = [[InlineKeyboardButton(text=lang.s.CLOSE_BUTTON, callback_data="close")]]


def main_menu():
    inline_keyboard = [
        [
            InlineKeyboardButton(
                text=lang.s.CORE,
                callback_data='corePanel'
            )
        ],
        [
            InlineKeyboardButton(
                text=lang.s.TELEGRAM,
                callback_data='tgPanel'
            )
        ],
        [
            InlineKeyboardButton(
                text=lang.s.PROVIDERS,
                callback_data='providerPanel'
            )
        ]
    ]
    # Show Rclone section if available
    if bot_set.rclone:
        inline_keyboard.append([
            InlineKeyboardButton(
                text="Rclone",
                callback_data='rclonePanel'
            )
        ])
    inline_keyboard += close_button
    return InlineKeyboardMarkup(inline_keyboard)


def providers_button():
    inline_keyboard = []

    # Always show Apple Music button
    inline_keyboard.append([
        InlineKeyboardButton("🍎 Apple Music", callback_data="appleP")
    ])

    # Conditionally show other providers
    if bot_set.qobuz:
        inline_keyboard.append([
            InlineKeyboardButton(lang.s.QOBUZ, callback_data="qbP")
        ])
    if bot_set.deezer:
        inline_keyboard.append([
            InlineKeyboardButton(lang.s.DEEZER, callback_data="dzP")
        ])
    if bot_set.can_enable_tidal:
        inline_keyboard.append([
            InlineKeyboardButton(lang.s.TIDAL, callback_data="tdP")
        ])

    inline_keyboard += main_button + close_button
    return InlineKeyboardMarkup(inline_keyboard)


def tg_button():
    inline_keyboard = [
        [
            InlineKeyboardButton(
                text=lang.s.BOT_PUBLIC.format(bot_set.bot_public),
                callback_data='botPublic'
            )
        ],
        [
            InlineKeyboardButton(
                text=lang.s.ANTI_SPAM.format(bot_set.anti_spam),
                callback_data='antiSpam'
            )
        ],
        [
            InlineKeyboardButton(
                text=lang.s.LANGUAGE,
                callback_data='langPanel'
            )
        ]
    ]

    inline_keyboard += main_button + close_button
    return InlineKeyboardMarkup(inline_keyboard)


def core_buttons():
    inline_keyboard = []

    if bot_set.rclone:
        inline_keyboard.append(
            [
                InlineKeyboardButton(
                    text=f"Return Link : {bot_set.link_options}",
                    callback_data='linkOptions'
                )
            ]
        )

    inline_keyboard += [
        [
            InlineKeyboardButton(
                text=f"Upload : {bot_set.upload_mode}",
                callback_data='upload'
            )
        ],
        [
            InlineKeyboardButton(
                text=f"Queue Mode: {'ON' if bot_set.queue_mode else 'OFF'}",
                callback_data='toggleQueueMode'
            )
        ],
    ]

    # Optional queue panel button
    if bot_set.queue_mode:
        inline_keyboard.append([
            InlineKeyboardButton(
                text="Open Queue Panel",
                callback_data='queuePanel'
            )
        ])

    inline_keyboard += [
        [
            InlineKeyboardButton(
                text=lang.s.SORT_PLAYLIST.format(bot_set.playlist_sort),
                callback_data='sortPlay'
            ),
            InlineKeyboardButton(
                text=lang.s.DISABLE_SORT_LINK.format(bot_set.disable_sort_link),
                callback_data='sortLinkPlay'
            )
        ],
        [
            InlineKeyboardButton(
                text=lang.s.PLAYLIST_ZIP.format(bot_set.playlist_zip),
                callback_data='playZip'
            ),
            InlineKeyboardButton(
                text=lang.s.PLAYLIST_CONC_BUT.format(bot_set.playlist_conc),
                callback_data='playCONC'
            )
        ],
        [
            InlineKeyboardButton(
                text=lang.s.ARTIST_BATCH_BUT.format(bot_set.artist_batch),
                callback_data='artBATCH'
            ),
            InlineKeyboardButton(
                text=lang.s.ARTIST_ZIP.format(bot_set.artist_zip),
                callback_data='artZip'
            )
        ],
        [
            InlineKeyboardButton(
                text=lang.s.ALBUM_ZIP.format(bot_set.album_zip),
                callback_data='albZip'
            ),
            InlineKeyboardButton(
                text=lang.s.POST_ART_BUT.format(bot_set.art_poster),
                callback_data='albArt'
            )
        ],
        [
            InlineKeyboardButton(
                text=f"Video Upload: {'Document' if bot_set.video_as_document else 'Media'}",
                callback_data='vidUploadType'
            )
        ],
        [
            InlineKeyboardButton(
                text=f"Extract Embedded Cover: {'True' if bot_set.extract_embedded_cover else 'False'}",
                callback_data='toggleExtractCover'
            )
        ],
        [
            InlineKeyboardButton(
                text=f"Safe Zip Names: {'ON' if bot_set.zip_name_use_underscores else 'OFF'}",
                callback_data='toggleSafeZipNames'
            )
        ]
    ]
    inline_keyboard += main_button + close_button
    return InlineKeyboardMarkup(inline_keyboard)


# New: Rclone settings buttons

def rclone_buttons():
    inline_keyboard = []

    # Show currently used remote:path
    current_remote = getattr(bot_set, 'rclone_remote', '') or '(unset)'
    current_path = getattr(bot_set, 'rclone_dest_path', '')
    current_display = f"{current_remote}:{current_path}" if current_path else (f"{current_remote}:" if current_remote != '(unset)' else '(unset)')
    inline_keyboard.append([
        InlineKeyboardButton(
            text=f"Using: {current_display}",
            callback_data='noop'
        )
    ])

    # Status line
    status_text = "Present" if os.path.exists('rclone.conf') else "Not found"
    inline_keyboard.append([
        InlineKeyboardButton(
            text=f"rclone.conf: {status_text}",
            callback_data='noop'
        )
    ])

    # Copy scope toggle
    inline_keyboard.append([
        InlineKeyboardButton(
            text=f"Copy Scope: {'Folder' if bot_set.rclone_copy_scope == 'FOLDER' else 'File'}",
            callback_data='rcloneScope'
        )
    ])

    # Import / Delete controls
    inline_keyboard.append([
        InlineKeyboardButton(
            text="Import rclone.conf",
            callback_data='rcloneImport'
        ),
        InlineKeyboardButton(
            text="Delete rclone.conf",
            callback_data='rcloneDelete'
        )
    ])

    # Actions: list remotes / send config
    inline_keyboard.append([
        InlineKeyboardButton(
            text="List remotes",
            callback_data='rcloneListRemotes'
        ),
        InlineKeyboardButton(
            text="Send rclone.conf",
            callback_data='rcloneSend'
        )
    ])

    # Cloud to cloud copy action
    inline_keyboard.append([
        InlineKeyboardButton(
            text="Cloud to Cloud Copy",
            callback_data='rcloneCloudCopyStart'
        )
    ])
    # Cloud to cloud move action
    inline_keyboard.append([
        InlineKeyboardButton(
            text="Cloud to Cloud Move",
            callback_data='rcloneCloudMoveStart'
        )
    ])

    # Destination controls (separate remote and path)
    dest_label = getattr(bot_set, 'rclone_dest', None) or (Config.RCLONE_DEST or '(unset)')
    inline_keyboard.append([
        InlineKeyboardButton(
            text="Select Remote",
            callback_data='rcloneSelectRemote'
        ),
        InlineKeyboardButton(
            text="Set Destination Path",
            callback_data='rcloneSetDestPath'
        )
    ])

    inline_keyboard += main_button + close_button
    return InlineKeyboardMarkup(inline_keyboard)


def language_buttons(languages, selected):
    inline_keyboard = []
    for item in languages:
        text = f"{item.__language__} ✅" if item.__language__ == selected else item.__language__
        inline_keyboard.append(
            [
                InlineKeyboardButton(
                    text=text.upper(),
                    callback_data=f'langSet_{item.__language__}'
                )
            ]
        )
    inline_keyboard += main_button + close_button
    return InlineKeyboardMarkup(inline_keyboard)

# Apple Music specific buttons

def apple_button(formats):
    """Create buttons for Apple Music settings"""
    buttons = []
    for fmt, label in formats.items():
        buttons.append([InlineKeyboardButton(label, callback_data=f"appleF_{fmt}")])
    buttons.append([InlineKeyboardButton("Quality Settings", callback_data="appleQ")])
    # Wrapper controls
    buttons.append([
        InlineKeyboardButton("🧩 Setup Wrapper", callback_data="appleSetup"),
        InlineKeyboardButton("⏹️ Stop Wrapper", callback_data="appleStop")
    ])
    buttons.append([InlineKeyboardButton("🔙 Back", callback_data="providerPanel")])
    return InlineKeyboardMarkup(buttons)

# Tidal panel
def tidal_buttons():
    status = '✅ ON' if bot_set.tidal_legacy_enabled else '❌ OFF'
    inline_keyboard = [
        [
            InlineKeyboardButton(
                text=f"Legacy Tidal: {status}",
                callback_data='toggleLegacyTidal'
            )
        ],
        [
            InlineKeyboardButton(
                text=lang.s.AUTHORIZATION,
                callback_data='tdAuth'
            )
        ]
    ]

    if bot_set.tidal:
        inline_keyboard.append(
            [
                InlineKeyboardButton(
                    text=lang.s.QUALITY,
                    callback_data='tdQ'
                )
            ]
        )

    inline_keyboard += main_button + close_button
    return InlineKeyboardMarkup(inline_keyboard)

def tidal_auth_buttons():
    inline_keyboard = []
    if bot_set.tidal:
        inline_keyboard += [
            [
                InlineKeyboardButton(
                    text=lang.s.TIDAL_REMOVE_LOGIN,
                    callback_data=f'tdRemove'
                )
            ],
            [
                InlineKeyboardButton(
                    text=lang.s.TIDAL_REFRESH_SESSION,
                    callback_data=f'tdFresh'
                )
            ]
        ]
    elif bot_set.can_enable_tidal:
        inline_keyboard.append(
            [
                InlineKeyboardButton(
                    text=lang.s.TIDAL_LOGIN_TV,
                    callback_data=f'tdLogin'
                )
            ]
        )
    inline_keyboard += main_button + close_button
    return InlineKeyboardMarkup(inline_keyboard)

# Qobuz qualities
def qb_button(qualities:dict):
    inline_keyboard = []
    for quality in qualities.values():
        inline_keyboard.append(
            [
                InlineKeyboardButton(
                    text=quality,
                    callback_data=f"qbQ_{quality.replace('✅', '')}"
                )
            ]
        )
    inline_keyboard += main_button + close_button
    return InlineKeyboardMarkup(inline_keyboard)

def tidal_quality_button(qualities:dict):
    inline_keyboard = []
    for quality in qualities.values():
        inline_keyboard.append(
            [
                InlineKeyboardButton(
                    text=quality,
                    callback_data=f"tdSQ_{quality.replace('✅', '')}"
                )
            ]
        )

    inline_keyboard.append(
        [
            InlineKeyboardButton(
                    text=F'SPATIAL : {bot_set.tidal.spatial}',
                    callback_data=f"tdSQ_spatial"
                )
        ]
    )
    inline_keyboard += main_button + close_button
    return InlineKeyboardMarkup(inline_keyboard)