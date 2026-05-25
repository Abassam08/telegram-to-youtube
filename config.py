import os
from dotenv import load_dotenv

load_dotenv()

# ── Telegram ──────────────────────────────────────────────────────────────────
TELEGRAM_API_ID   = int(os.getenv("TELEGRAM_API_ID", "0"))
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH", "")
TELEGRAM_CHANNEL  = os.getenv("TELEGRAM_CHANNEL", "")  # e.g. "@channelname" or numeric id
TELEGRAM_SESSION  = "data/telegram_session"

# ── Daily limits ──────────────────────────────────────────────────────────────
MAX_DOWNLOADS_PER_DAY = 10
MAX_UPLOADS_PER_DAY   = 6

# ── Local temp storage ────────────────────────────────────────────────────────
TEMP_DOWNLOAD_DIR = "data/temp"

# ── SQLite ────────────────────────────────────────────────────────────────────
DB_PATH = "data/videos.db"

# ── Google Drive (two accounts share the same OAuth client secrets) ───────────
DRIVE_CLIENT_SECRETS = "credentials/drive_client_secrets.json"
DRIVE_FOLDER_NAME    = "telegram-videos"
DRIVE_ACCOUNTS = [
    {
        "name":        "account1",          # abassam912@gmail.com — primary
        "token_file":  "credentials/drive_token1.json",
        "capacity_gb": 122,
    },
    {
        "name":        "account2",          # ahmedindiaytube2025@gmail.com — secondary
        "token_file":  "credentials/drive_token2.json",
        "capacity_gb": 150,
    },
]

# ── Gemini ────────────────────────────────────────────────────────────────────
GEMINI_API_KEY = os.getenv("GOOGLE_GEMINI_API_KEY", "")
GEMINI_MODEL   = "gemini-flash-lite-latest"

# ── YouTube ───────────────────────────────────────────────────────────────────
YOUTUBE_CLIENT_SECRETS = "credentials/youtube_client_secrets.json"
YOUTUBE_TOKEN          = "credentials/youtube_token.json"
YOUTUBE_CATEGORY_ID    = "22"    # People & Blogs
YOUTUBE_PRIVACY        = "public"  # public | private | unlisted
YOUTUBE_FIXED_TAGS: list[str] = [
    "مسيحي", "يسوع", "مصر", "معاذ عليان", "محمود داوود", "زين_خير_الله", "الكنيسة"
]

# ── Scheduler (24-hour format) ────────────────────────────────────────────────
DOWNLOAD_HOUR = 3                        # download job fires at 03:00 daily
UPLOAD_HOURS  = [4, 7, 13, 14, 16, 21]     # one upload per entry, spread across the day
