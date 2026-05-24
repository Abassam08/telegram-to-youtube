"""Run from the project root to verify all services are reachable."""
import asyncio
import json
import os
import sys

# ── DB ────────────────────────────────────────────────────────────────────────
def check_db():
    import db.database as database
    os.makedirs(os.path.dirname(os.path.abspath("data/videos.db")), exist_ok=True)
    database.init_db()
    # smoke-test every public helper
    database.video_exists(0)
    database.count_downloads_today()
    database.count_uploads_today()
    database.get_pending_uploads()
    print("  DB           ✅  data/videos.db initialised")

# ── Telegram ──────────────────────────────────────────────────────────────────
async def _check_telegram():
    from telethon import TelegramClient
    import config
    async with TelegramClient(
        config.TELEGRAM_SESSION, config.TELEGRAM_API_ID, config.TELEGRAM_API_HASH
    ) as client:
        me      = await client.get_me()
        entity  = await client.get_entity(config.TELEGRAM_CHANNEL)
        title   = getattr(entity, "title", config.TELEGRAM_CHANNEL)
        print(f"  Telegram     ✅  signed in as @{me.username}  |  channel: {title}")

def check_telegram():
    asyncio.run(_check_telegram())

# ── Google Drive ──────────────────────────────────────────────────────────────
def check_drive():
    import config
    from googleapiclient.discovery import build
    from google.oauth2.credentials import Credentials

    for account in config.DRIVE_ACCOUNTS:
        creds   = Credentials.from_authorized_user_file(
            account["token_file"],
            ["https://www.googleapis.com/auth/drive"],
        )
        service = build("drive", "v3", credentials=creds)
        quota   = service.about().get(fields="user,storageQuota").execute()
        email   = quota["user"]["emailAddress"]
        q       = quota["storageQuota"]
        used_gb = int(q.get("usage", 0))  / (1024**3)
        total_gb= int(q.get("limit", 0))  / (1024**3)
        free_gb = total_gb - used_gb
        print(
            f"  Drive ({account['name']})  ✅  {email}"
            f"  |  {used_gb:.1f} / {total_gb:.0f} GB used"
            f"  |  {free_gb:.1f} GB free"
        )

# ── YouTube ───────────────────────────────────────────────────────────────────
def check_youtube():
    import config
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    creds = Credentials.from_authorized_user_file(
        config.YOUTUBE_TOKEN,
        ["https://www.googleapis.com/auth/youtube.upload"],
    )
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    if not creds.valid:
        raise RuntimeError("token is invalid or expired — re-run auth_youtube.py")
    email = creds.client_id  # not the account email but confirms token loaded
    print(f"  YouTube      ✅  token valid  |  scopes={creds.scopes}")

# ── Gemini ────────────────────────────────────────────────────────────────────
def check_gemini():
    import config
    from google import genai

    client = genai.Client(api_key=config.GEMINI_API_KEY)
    resp   = client.models.generate_content(model=config.GEMINI_MODEL, contents="Reply with just: ok")
    reply  = resp.text.strip()
    print(f"  Gemini       ✅  model={config.GEMINI_MODEL}  reply='{reply}'")

# ── Main ──────────────────────────────────────────────────────────────────────
CHECKS = [
    ("Database",  check_db),
    ("Telegram",  check_telegram),
    ("Drive",     check_drive),
    ("YouTube",   check_youtube),
    ("Gemini",    check_gemini),
]

errors = []
print("\nVerifying services…\n")
for name, fn in CHECKS:
    try:
        fn()
    except Exception as exc:
        print(f"  {name:<12} ❌  {exc}")
        errors.append(name)

print()
if errors:
    print(f"Failed: {', '.join(errors)}")
    sys.exit(1)
else:
    print("All services OK — ready to run main.py")
