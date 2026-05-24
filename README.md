# telegram-to-youtube

Automated pipeline that downloads videos from a Telegram channel, stores them on Google Drive, generates Arabic titles and tags with Claude, then publishes them to YouTube — 10 downloads and 5 uploads per day, with SQLite deduplication.

## Architecture

```
Telegram channel
      │  telethon (≤10/day)
      ▼
 data/temp/          ← local scratch space, files deleted after Drive upload
      │  google-api-python-client
      ▼
 Google Drive        ← two accounts used in order of available space
      │  anthropic SDK  (title + tags generated once, stored in DB)
      │  youtube Data API v3 (≤5/day, one per scheduled slot)
      ▼
   YouTube
      │  after confirmed upload
      ▼
 Drive file deleted  ← DB record kept forever for deduplication
```

## Project structure

```
telegram-to-youtube/
├── config.py                  # all tuneable settings
├── main.py                    # APScheduler orchestrator
├── requirements.txt
├── .env.example
├── db/
│   └── database.py            # SQLite helpers
├── services/
│   ├── telegram_downloader.py
│   ├── drive_manager.py
│   ├── claude_generator.py
│   └── youtube_uploader.py
├── utils/
│   └── logger.py
├── credentials/               # put JSON key/token files here (git-ignored)
└── data/                      # runtime data — DB, temp files, session (git-ignored)
```

## Setup

### 1. Install dependencies

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Environment variables

```bash
cp .env.example .env
# fill in TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_CHANNEL, ANTHROPIC_API_KEY
```

### 3. Telegram auth (one-time)

On first run Telethon will prompt for your phone number and a code sent to the account. Run this once interactively so the session file is saved to `data/telegram_session`:

```bash
python - <<'EOF'
import asyncio, config
from telethon import TelegramClient
async def auth():
    async with TelegramClient(config.TELEGRAM_SESSION, config.TELEGRAM_API_ID, config.TELEGRAM_API_HASH) as c:
        print("Authorised as", (await c.get_me()).username)
asyncio.run(auth())
EOF
```

### 4. Google Drive OAuth (one-time per account)

1. Create a Google Cloud project and enable the **Google Drive API**.
2. Download the OAuth 2.0 client secrets as `credentials/drive_client_secrets.json`.
3. Authorize account 1 — a browser window will open:

```bash
python - <<'EOF'
import config
from services.drive_manager import _get_service
_get_service(config.DRIVE_ACCOUNTS[0])
print("Account 1 authorised")
EOF
```

4. Sign out of Google in the browser, then authorize account 2:

```bash
python - <<'EOF'
import config
from services.drive_manager import _get_service
_get_service(config.DRIVE_ACCOUNTS[1])
print("Account 2 authorised")
EOF
```

Tokens are saved to `credentials/drive_token1.json` and `credentials/drive_token2.json`.

### 5. YouTube OAuth (one-time)

1. Enable the **YouTube Data API v3** in your Google Cloud project.
2. Download OAuth 2.0 client secrets as `credentials/youtube_client_secrets.json`.
3. Authorize:

```bash
python - <<'EOF'
from services.youtube_uploader import _get_service
_get_service()
print("YouTube authorised")
EOF
```

Token is saved to `credentials/youtube_token.json`.

### 6. Run

```bash
python main.py
```

The scheduler fires the download job at `DOWNLOAD_HOUR` (default 06:00) and upload jobs at each hour in `UPLOAD_HOURS` (default 08:00, 11:00, 14:00, 17:00, 20:00).

To run as a background service on Linux with systemd:

```ini
# /etc/systemd/system/tg2yt.service
[Unit]
Description=Telegram → YouTube pipeline

[Service]
WorkingDirectory=/path/to/telegram-to-youtube
ExecStart=/path/to/telegram-to-youtube/.venv/bin/python main.py
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload && sudo systemctl enable --now tg2yt
```

## Configuration reference (`config.py`)

| Setting | Default | Description |
|---|---|---|
| `MAX_DOWNLOADS_PER_DAY` | 10 | Telegram download cap |
| `MAX_UPLOADS_PER_DAY` | 5 | YouTube upload cap |
| `DOWNLOAD_HOUR` | 6 | Hour (0–23) to run download job |
| `UPLOAD_HOURS` | `[8,11,14,17,20]` | Hours to attempt one upload each |
| `YOUTUBE_PRIVACY` | `"public"` | `public` / `private` / `unlisted` |
| `YOUTUBE_CATEGORY_ID` | `"22"` | YouTube category (22 = People & Blogs) |
| `YOUTUBE_DEFAULT_TAGS` | `[]` | Tags appended to every video |
| `DRIVE_FOLDER_NAME` | `"telegram-videos"` | Folder created in each Drive account |

## DB schema

Table `videos`:

| Column | Type | Notes |
|---|---|---|
| `telegram_message_id` | INTEGER UNIQUE | deduplication key |
| `status` | TEXT | `pending` → `downloading` → `downloaded` → `on_drive` → `uploading` → `uploaded` / `failed` |
| `drive_file_id` | TEXT | set after Drive upload, used for download + delete |
| `drive_account` | TEXT | `account1` or `account2` |
| `youtube_video_id` | TEXT | set after confirmed upload |
| `youtube_title` | TEXT | Arabic title from Claude |
| `youtube_tags` | TEXT | JSON array of Arabic tags |
| `download_date` | TEXT | YYYY-MM-DD, used for daily cap |
| `upload_date` | TEXT | YYYY-MM-DD, used for daily cap |
