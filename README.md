
# Project-Siesta
![GitHub Repo stars](https://img.shields.io/github/stars/vinayak-7-0-3/Project-Siesta?style=for-the-badge)
![GitHub forks](https://img.shields.io/github/forks/vinayak-7-0-3/Project-Siesta?style=for-the-badge)
![Docker Pulls](https://img.shields.io/docker/pulls/weebzbots/project-siesta?style=for-the-badge)
[![Static Badge](https://img.shields.io/badge/support-pink?style=for-the-badge)](https://t.me/weebzgroup)

AIO Bot for your music needs on Telegram.

Note: This is not a music streaming / VC Bot

## FEATURES

**Currently the project is in early development stage and features are incomplete**

- **Flexible Database Support:** Choose between PostgreSQL and MongoDB for your database backend.

Feels free to check the repo and report bugs / features

**A complete guide for ~~downloading~~ (coughs..) ehmm.... can be found [here](https://rentry.org/project-siesta)**

## INSTALLATION


#### 1) LOCAL DEPLOYMENT

**Requirements**
- Python>=3.10 (3.12 recommended) 
- Git installed (optional)
- Rclone (optional)
- ffmpeg (optional)

**Steps**
- Git clone (or download) the repo
- Create virtual environment and run
```
virtualenv -p python3 VENV
. ./VENV/bin/activate
```
- Edit and fill out the essentials environment variables in `sample.env` (refer [here](#variables-info))
- Rename `sample.env` to `.env`
- Finally run
```
pip install -r requirements.txt
python -m bot
```

#### 2) USING DOCKER (Manual Build)
**Requirements**
- Git installed (optional)
- Of course Docker installed (how would ya do docker method without docker  🤷‍)

**Steps**
- Git clone (or download) the repo
- Fill out the required variables in `sample.env` (refer [here](#variables-info))
- Build the image using the Docker build command
```
sudo docker build . -t project-siesta
```
- Now run the created Docker image
```
sudo docker run -d --env-file sample.env --name siesta project-siesta
```
- At this point your bot will be running (if everything correct)

#### 3) USING DOCKER (Prebuilt Image)

Premade Docker Images are available at Dockerhub repo `weebzbots/project-siesta`
These images are made using GitHub Actions
- Supported architectures
	- `arm64`
	- `amd64`
- Build Tags
	- `latest` - Latest stable releases from main branch
	- `beta` - Latest beta releases from beta branch (early feature testing)
	- `<commit-hash>` - You can use specific commit hash for specific versions

**Requirements**
- Of course Docker installed (how would ya do docker method without docker  🤷‍)

**Steps**
- Pull the Docker image
```
sudo docker pull weebzcloud/project-siesta
```
- Somewhere in your server, create a `.env` file with required variables (refer [here](#variables-info))
- Run the image
```
sudo docker run -d --env-file .env --name siesta project-siesta
```
- At this point your bot will be running (if everything correct)

## VARIABLES INFO

#### ESSENTIAL VARIABLES
- `TG_BOT_TOKEN` - Telegeam bot token (get it from [BotFather](https://t.me/BotFather))
- `APP_ID` - Your Telegram APP ID (get it from my.telegram.org) `(int)`
- `API_HASH` - Your Telegram APP HASH (get it from my.telegram.org) `(str)`
- `DATABASE_TYPE` - (Optional) The type of database to use. Can be `postgres` or `mongodb`. Defaults to `postgres`. `(str)`
- `DATABASE_URL` - The connection URL for your chosen database. Make sure this matches the `DATABASE_TYPE` (e.g., `postgresql://...` for postgres, `mongodb://...` for mongodb). `(str)`
- `MONGODB_DATABASE` - (Optional) If using MongoDB, you can specify the database name here. This is required if the database name is not in the `DATABASE_URL`. `(str)`
- `BOT_USERNAME` - Your Telegram Bot username (with or without `@`) `(str)`
- `ADMINS` - List of Admin users for the Bot (seperated by space) `(str)`

#### OPTIONAL VARIABLES
- `DOWNLOAD_BASE_DIR` - Downloads folder for the bot (folder is inside the working directory of bot) `(str)`
- `LOCAL_STORAGE` - Folder (full path needed) where you want to store the downloaded file the server itself rather than uploading `(str)`
- `RCLONE_CONFIG` - Rclone config as text or URL to file (can ignore this if you add file manually to root of repo) `(str)`
- `RCLONE_DEST` - Rclone destination as `remote-name:folder-in-remote` `(str)`
- `INDEX_LINK` - If index link needed for Rclone uploads (testes with alist) (no trailing slashes `/` ) `(str)`
- `MAX_WORKERS` - Multithreading limit (kind of more speed) `(int)`
- `TRACK_NAME_FORMAT` - Naming format for tracks (check [metadata](https://github.com/vinayak-7-0-3/Project-Siesta/blob/2bbea8572d660a92bb182a360e91791583f4523b/bot/helpers/metadata.py#L16) section for tags supported) `(str)`
- `PLAYLIST_NAME_FORMAT` - Similar to `TRACK_NAME_FORMAT` but for Playlists (Note: all tags might not be available) `(str)`
- `TIDAL_NG_DOWNLOAD_PATH` - Overrides the download path for the Tidal NG provider. If set, all Tidal NG downloads will be saved here, bypassing other settings. `(str)`

## CREDITS
- OrpheusDL - https://github.com/yarrm80s/orpheusdl
- Streamrip - https://github.com/nathom/streamrip
- yaronzz - Tidal-Media-Downloader - https://github.com/yaronzz/Tidal-Media-Downloader
- vitiko98 - qobuz-dl - https://github.com/vitiko98/qobuz-dl

## Support Me ❤️
[![ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/I2I7FWQZ4)

TON - `UQBBPkWSnbMWXrM6P-pb96wYxQzLjZ2hhuYfsO-N2pVmznCG`

## Tidal NG Downloader (Beta)

This bot features a modern, robust backend for handling Tidal downloads, referred to as "Tidal NG" (Next Generation). It operates by interfacing with a powerful external command-line tool, `tidal-dl-ng`.

### How It Works

Unlike the legacy provider which used a Python library directly, the Tidal NG handler acts as a smart controller for the `tidal-dl-ng` CLI tool. When you request a Tidal download:
1.  The bot determines the correct, isolated directory for the current download task.
2.  It programmatically modifies the `tidal-dl-ng` tool's own `settings.json` file to set the `download_base_path` and any user-specific settings.
3.  It executes the CLI tool (`python cli.py dl <URL>`), which then downloads the music to the location specified by the bot.
4.  After the download is complete or fails, the bot restores the `settings.json` file to its original state to ensure system integrity.

**Note on First Use**: The configuration directory (`/root/.config/tidal_dl_ng/`) and `settings.json` file for the tool are created automatically the first time you use any Tidal NG feature. No manual setup is required.

### Configuration & Settings

Configuration for the Tidal NG provider is now handled via direct commands, which gives you full, real-time control over the `settings.json` file. This is the same robust method used for the Apple Music provider.

-   **Accessing Settings**: Navigate to `/settings` -> `Provider Settings` -> `Tidal NG`.
-   This menu provides important action buttons and explains how to use the new command-based system.

-   **Utility Buttons**:
    -   `🔑 Login` / `🚨 Logout`: Manage your `tidal-dl-ng` session.
    -   `📂 Import Config File`: For advanced users, this allows you to upload configuration files (e.g., `token.json`) directly into the Tidal NG configuration directory.
    -   `⚙️ Execute cfg`: Displays the tool's current configuration or generates a new default one if it's missing. This is useful for seeing all available keys.

-   **New Commands for Real-time Control**:
    -   `/tidal_ng_config` or `/tncfg`: Shows help and a list of example keys.
    -   `/tidal_ng_get <key>`: Shows the current value of a specific key in `settings.json`.
    -   `/tidal_ng_set <key> <value>`: Sets a key to a specific value. The bot will validate the input for known keys.
    -   `/tidal_ng_toggle <key>`: Toggles a boolean key between `true` and `false`.
    -   `/tidal_ng_show [keys...]`: Shows the entire `settings.json` file, or just the specified keys.

This new system replaces the old, non-functional UI buttons and gives you complete control. As a result, the bot no longer uses any per-user settings from its own database for Tidal NG downloads; it relies entirely on the `settings.json` file that you manage with these commands.

### Important Notes
- **FFmpeg Path**: The bot will always forcefully set the `path_binary_ffmpeg` to `/usr/bin/ffmpeg` before every download to ensure video processing and FLAC extraction works reliably. You do not need to set this key yourself.
- **Download Path**: The bot will always set the `download_base_path` to a temporary, per-task directory to ensure downloads do not conflict. The `TIDAL_NG_DOWNLOAD_PATH` environment variable can still be used to override this.
    - New: You can now override the Tidal NG `download_base_path` via environment: `TIDAL_NG_DOWNLOAD_BASE_PATH`. This takes precedence over `settings.json` (legacy `TIDAL_NG_DOWNLOAD_PATH` also supported).
    - New: A top-of-panel toggle, “Preset Buttons: ON/OFF”, lets you temporarily hide the cycling/toggle preset buttons to avoid accidental changes. Interactive JSON commands (`/tidal_ng_*`) remain available.

## Apple Wrapper Controls (Apple Music)

- **Location**: `Settings -> Providers -> Apple Music`
- **Buttons**:
  - `🧩 Setup Wrapper`: Starts an interactive setup that asks for your Apple ID username and password, then runs the wrapper setup script with those credentials. If 2FA is required, the bot will detect it and prompt you to send the 2FA code, then continues automatically.
  - `⏹️ Stop Wrapper`: Stops any running wrapper process. Includes a confirmation step to prevent accidental taps.

### How Setup Works
1. Tap `🧩 Setup Wrapper`.
2. Send your Apple ID username when asked.
3. Send your Apple ID password when asked.
4. The bot runs the setup script with `USERNAME` and `PASSWORD` exported in the environment, equivalent to:
   ```bash
   USERNAME="your_username" PASSWORD="your_password" /usr/src/app/downloader/setup_wrapper.sh
   ```
5. If the wrapper requests 2FA, you will see a prompt. Send the 2FA code as a normal message within 3 minutes.
6. On success, you'll get a confirmation. On failure, the last part of the script output is shown for debugging.

### How Stop Works
- Tap `⏹️ Stop Wrapper` -> Confirm. The bot runs:
  ```bash
  /usr/src/app/downloader/stop_wrapper.sh
  ```
- It kills wrapper processes and frees ports 10020/20020.

### Configuration
- Override script paths with env vars if needed:
  - `APPLE_WRAPPER_SETUP_PATH` (default `/usr/src/app/downloader/setup_wrapper.sh`)
  - `APPLE_WRAPPER_STOP_PATH` (default `/usr/src/app/downloader/stop_wrapper.sh`)

### Notes & Security
- Credentials are only used to start the setup process and are not stored by the bot.
- You can cancel the flow any time by sending `/cancel`.
- If 2FA prompt does not appear (rare), setup continues and completes automatically.

## Apple Music Controls (enhanced)

The Apple provider now has its own zip controls and a rich settings panel driven by `config.yaml` (as used by `zhaarey/apple-music-downloader`).

- Apple-specific zip toggles (independent from core):
  - Zip Albums (Apple)
  - Zip Playlists (Apple)

- Config panel buttons (mutate `APPLE_CONFIG_YAML_PATH`):
  - Cover: size (1000/3000/5000), format (jpg/png/original), embed cover, save artist cover
  - Lyrics: type (lyrics/syllable-lyrics), format (lrc/ttml), embed lyrics, save lyrics file
  - Animated artwork: save animated artwork, emby animated artwork
  - Music video: MV audio type (atmos/ac3/aac), MV max (1080/1440/2160)
  - Playlist helpers: download album cover for playlist, use songinfo for playlist
  - Concurrency: `limit-max` (cycle common values)
  - Naming: album folder format presets, playlist folder format presets, song file format presets

Commands `/config_get`, `/config_set`, `/config_toggle`, `/config_show` still work and write to `config.yaml` safely with backups.

### Flags Popup for Apple /download

- Enable in Settings → Providers → Apple Music → “Flags Popup”.
- When ON, sending `/download <apple_url>` opens a quick picker to avoid typing flags:
  - Single track: applies `--song`
  - Atmos album: applies `--atmos`
  - Atmos track: applies `--song --atmos`
- The popup closes after selection or cancel. When OFF, manual flags still work (e.g., `/download --song <url>`).

### Guard against accidental touches

- A top-of-panel toggle, “Preset Buttons: ON/OFF”, hides the cycling/toggle preset buttons in the Apple panel to prevent accidental config edits. The interactive editor remains available.

### File Management

The Apple Music panel also includes tools for managing the downloader's internal files located in the `/root/amalac/` directory.

-   **`📂 Manage Files`**: Opens an interactive, button-based file browser for the `/root/amalac/` directory.
    -   Navigate into sub-folders.
    -   Select a file to get options to **Download** it to your chat or **Delete** it from the server (with confirmation).
    -   Use the "Up" and "Back" buttons to navigate the file system.

-   **`📂 Import File`**: Allows you to upload a file directly to the `/root/amalac/` directory.
    -   After tapping the button, the bot will ask you to send a document.
    -   The uploaded file will be saved in `/root/amalac`.
    -   If a file with the same name already exists, it will be automatically overwritten.

## Commands and Usage

These commands work in any chat where the bot is present. Copy-paste directly into Telegram.

- /start: Show welcome message
- /help: Show available commands
- /settings: Open settings panel (Provider panels include Tidal NG JSON and Apple YAML configurators)
- /download <url> [--options]: Start a download for a supported provider
This build is Apple Music–only. Qobuz, Tidal, and Deezer integrations have been removed. Use Apple Music links like `https://music.apple.com/...`.
  - Examples:
    - ```
/download https://music.apple.com/…
    ```
    - ```
/download --alac-max 192000 https://music.apple.com/…
    ```
    - Reply to a message containing the link and send:
      ```
/download --atmos
      ```
  - On start, the bot replies with a Task ID. Use it to manage the task.
- Queue Mode (sequential downloads/uploads):
  - Turn on: Settings → Core → Queue Mode: ON
  - While ON, /download does not start immediately; it enqueues and replies with a Queue ID and position.
  - See your queue: use /qqueue (alias /queue) or Settings → Core → Open Queue Panel
  - Cancel a queued link: /qcancel <queue_id> or use the ❌ button in Queue Panel
  - Cancel the currently running job: /cancel <task_id>
- /cancel <task_id>: Cancel a specific running task by its ID
  - Example:
    ```
/cancel ab12cd34
    ```
- /cancel_all: Cancel all your running tasks (download, zipping, uploading)
  - Example:
    ```
/cancel_all
    ```

### Core Settings Panel

The main settings panel (`/settings`) contains several core toggles that affect the bot's general behavior.

-   **`Safe Zip Names`**: Controls how zip file names are created for all providers.
    -   **ON (Default):** Replaces spaces in album/playlist titles with underscores (`_`) for better compatibility. E.g., `My Album` -> `My_Album.zip`.
    -   **OFF:** Keeps original spaces in the filename. E.g., `My Album.zip`.

### What happens on cancel
- The bot stops the active step (downloading, zipping, uploading)
- Any partial files/archives are cleaned up automatically
- The progress message is updated to indicate cancellation

### Realtime system usage in progress
- Progress messages now include CPU, RAM, and Disk usage to help monitor server load while tasks run.

## Apple Music Config (config.yaml) via Telegram

Admins can view and edit `/root/amalac/config.yaml` in real time. Changes are written safely with a backup created each time.

Path override: set env `APPLE_CONFIG_YAML_PATH` to a different file if needed.

### Commands

- /config or /cfg: Show quick help and path
- /config_show [keys...]: Show current values for a curated list or specific keys
- /config_get <key>: Show current value of a key (sensitive values are masked)
- /config_set <key> <value>: Set key to value (with validation where applicable)
- /config_toggle <bool-key>: Toggle a boolean key between true/false

### Supported Keys and Validation

- Choice keys:
  - lrc-type: lyrics | syllable-lyrics
  - lrc-format: lrc | ttml
  - cover-format: jpg | png | original
  - mv-audio-type: atmos | ac3 | aac
- Boolean keys:
  - embed-lrc
  - save-lrc-file
  - save-artist-cover
  - save-animated-artwork
  - emby-animated-artwork
  - embed-cover
  - dl-albumcover-for-playlist
- Integer keys:
  - mv-max (e.g., 2160)
- Sensitive keys (masked in outputs; will be auto-quoted on set):
  - media-user-token
  - authorization-token

Other common keys you can set directly with /config_set:
- cover-size (e.g., `5000x5000`)
- alac-save-folder, atmos-save-folder, aac-save-folder (folders are auto-created if missing)
- alac-max, atmos-max, aac-type, storefront, language

### Examples

```text
/config_show
/config_get storefront
/config_set storefront in
/config_set lrc-type lyrics
/config_set lrc-format lrc
/config_toggle embed-lrc
/config_toggle save-artist-cover
/config_set cover-format png
/config_set cover-size 5000x5000
/config_set mv-audio-type atmos
/config_set mv-max 2160
/config_set media-user-token "<your_token_here>"
/config_set alac-save-folder "/usr/src/app/bot/DOWNLOADS/5329535193/Apple Music/alac"
```

Note: If the Apple downloader runs persistently, restart it after updating critical values (tokens, formats) so it reloads the file.

## BotFather command list (copy-paste)

```text
start - Start the bot
help - Show help
settings - Open settings panel
download - Start a download
queue - Show your queue
qqueue - Show your queue (alias)
qcancel - Cancel a queued item by Queue ID
cancel - Cancel a running task by ID
cancel_all - Cancel all your running tasks
config - Config help for Apple Music YAML
config_show - Show config values (or specific keys)
config_get - Get a single config value
config_set - Set a config value
config_toggle - Toggle a boolean config value
tidal_ng_config - Config help for Tidal NG JSON
tncfg - Alias for tidal_ng_config
tidal_ng_show - Show Tidal NG config values
tidal_ng_get - Get a single Tidal NG config value
tidal_ng_set - Set a Tidal NG config value
tidal_ng_toggle - Toggle a boolean Tidal NG config value
log - Get the bot log
auth - Authorize a user or chat
ban - Ban a user or chat
```