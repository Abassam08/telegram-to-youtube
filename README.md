# telegram-to-youtube

Automated pipeline that monitors a Telegram channel, downloads new videos, generates Arabic metadata with Google Gemini AI, and publishes them to YouTube — fully unattended, running on a free Oracle Cloud VM.

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Architecture](#2-architecture)
3. [Tech Stack](#3-tech-stack)
4. [Prerequisites](#4-prerequisites)
5. [Step-by-step Setup Guide](#5-step-by-step-setup-guide)
6. [Configuration Reference](#6-configuration-reference)
7. [Deployment on Oracle Cloud Free Tier](#7-deployment-on-oracle-cloud-free-tier)
8. [Scheduler Explained](#8-scheduler-explained)
9. [Database Schema](#9-database-schema)
10. [Troubleshooting](#10-troubleshooting)
11. [Future Improvements](#11-future-improvements)

---

## 1. Project Overview

### What it does

This project automates the full lifecycle of reposting Arabic Christian video content from a private Telegram channel to a public YouTube channel:

1. **Downloads** up to 10 videos per day from a Telegram channel using the Telethon library, saving them to `data/temp/`
2. **Generates** an Arabic YouTube title, description, tags, and hashtags using the Google Gemini API — based on the video's original Telegram caption — in the same step as the download
3. **Uploads** videos to YouTube at scheduled intervals (up to 6 per day), directly from `data/temp/`, spread across the day to avoid quota issues
4. **Cleans up** the local temp file after a confirmed YouTube upload
5. **Tracks** every video in a local SQLite database to prevent duplicate downloads or uploads — forever

### Why it was built

Managing a YouTube channel that reposts content from Telegram is tedious when done manually: downloading files, writing Arabic titles, adding tags, scheduling uploads. This project eliminates all of that. It runs continuously on a free Oracle Cloud VM, wakes up on a schedule, and handles everything automatically — including detecting YouTube Shorts (videos under 60 seconds) and formatting their metadata differently.

### Google Drive

Google Drive is **not required** for normal operation. The pipeline downloads directly to `data/temp/` and uploads from there to YouTube. Drive credentials are only used as a backward-compatibility path for any existing DB records that already have a `drive_file_id` from a previous pipeline version.

---

## 2. Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Telegram Channel                         │
│                        @memovideos                              │
└──────────────────────────────┬──────────────────────────────────┘
                               │  Telethon  (≤10 videos/day)
                               ▼
                    ┌─────────────────────┐
                    │   data/temp/        │  Local storage
                    │   (video file)      │  File deleted after YouTube upload
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │  Gemini AI           │  Runs immediately after download,
                    │  (metadata gen)      │  in the same download_job() call
                    │                      │
                    │  • Arabic title      │
                    │  • Description       │
                    │  • Tags              │
                    │  • Hashtags          │
                    └──────────┬───────────┘
                               │  (all metadata saved to SQLite, status = on_drive)
                               │
                               │  At each upload slot (≤6/day)
                               ▼
                    ┌──────────────────────┐
                    │   YouTube Channel    │
                    │   (public upload)    │
                    │   direct from        │
                    │   data/temp/         │
                    └──────────┬───────────┘
                               │  After confirmed upload
                               ▼
                    Local file deleted  ──►  SQLite record kept forever
                                             (prevents re-download)
```

### Data flow summary

| Step | What happens | Where |
|------|-------------|-------|
| 1 | Scheduler wakes at 03:00 Cairo time | `main.py` |
| 2 | Fetch new video messages from Telegram | `telegram_downloader.py` |
| 3 | Skip message IDs already in DB | `database.py` |
| 4 | Download video to `data/temp/` | `telegram_downloader.py` |
| 5 | Generate title, description, tags, hashtags via Gemini | `claude_generator.py` |
| 6 | Save all metadata to SQLite, set `status = on_drive` | `database.py` |
| 7 | At each upload slot: upload directly from `data/temp/` to YouTube | `youtube_uploader.py` |
| 8 | Mark DB record as `uploaded`, delete local temp file | `main.py` |

> **Steps 4–6 all happen inside `download_job()`** — by the time the job finishes, every downloaded video already has its full metadata in the DB and is ready to upload.

---

## 3. Tech Stack

| Component | Tool / Library | Purpose |
|-----------|---------------|---------|
| Telegram client | `telethon` 1.43+ | Download videos from Telegram channels |
| AI metadata | `google-genai` (Gemini) | Generate Arabic titles, tags, hashtags |
| YouTube upload | YouTube Data API v3 | Publish videos with full metadata |
| Scheduler | `APScheduler` 3.11+ | Cron-based download and upload jobs |
| Database | SQLite (stdlib) | Deduplication and state tracking |
| Config | `python-dotenv` | Load secrets from `.env` |
| VM provisioning | `oci` SDK | Auto-retry Oracle A1.Flex instance creation |
| Runtime | Python 3.12 | Minimum Python 3.10 required |

---

## 4. Prerequisites

Before starting, you need accounts and access to the following:

| Requirement | Where to get it | Notes |
|-------------|----------------|-------|
| Telegram account | telegram.org | Must be a real account (not a bot) to read channels |
| Telegram API credentials | my.telegram.org/apps | Free, instant |
| Google account for YouTube | google.com | The channel you want to upload to |
| Google Cloud project | console.cloud.google.com | Free tier is sufficient |
| Gemini API key | aistudio.google.com | Free tier available |
| Python 3.10+ | python.org | With `pip` and `venv` |

---

## 5. Step-by-step Setup Guide

### a. Telegram API Setup

1. Go to **https://my.telegram.org/apps** and sign in with your Telegram phone number
2. Click **"Create new application"**
3. Fill in any app name and short name (e.g. `video-bot`)
4. Copy the **`api_id`** (a number) and **`api_hash`** (a hex string)
5. Note the username or numeric ID of the Telegram channel you want to monitor (e.g. `@memovideos`)

These go into your `.env` file as `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, and `TELEGRAM_CHANNEL`.

---

### b. Google Cloud Project Setup

1. Go to **https://console.cloud.google.com**
2. Click the project dropdown at the top → **"New Project"**
3. Name it anything (e.g. `telegram-youtube-bot`) → **Create**
4. Wait for it to be created, then make sure it is selected in the dropdown

---

### c. Enable YouTube Data API v3

From inside your Google Cloud project:

1. Go to **APIs & Services → Library**
2. Search for **"YouTube Data API v3"** → click it → **Enable**

---

### d. OAuth Consent Screen Configuration

Before you can create OAuth credentials, Google requires an OAuth consent screen:

1. Go to **APIs & Services → OAuth consent screen**
2. Select **"External"** user type → **Create**
3. Fill in:
   - **App name**: anything (e.g. `TG2YT Bot`)
   - **User support email**: your email
   - **Developer contact**: your email
4. Click **Save and Continue** through the Scopes page (no scopes needed here)
5. On the **Test users** page, add your YouTube channel account email
6. Click **Save and Continue** → **Back to Dashboard**

> **Why test users?** While the app is in "Testing" mode, only listed test users can authorize it. You do not need to publish the app.

---

### e. Creating OAuth Credentials

#### YouTube credentials

1. Go to **APIs & Services → Credentials** → **Create Credentials → OAuth client ID**
2. Application type: **Desktop app**
3. Name: `YouTube Client`
4. Click **Create** → **Download JSON**
5. Save the downloaded file as: `credentials/youtube_client_secrets.json`

---

### f. Authorizing YouTube (one-time)

```bash
python auth_youtube.py
```

Sign in as your **YouTube channel account**. Token saved to `credentials/youtube_token.json`.

---

### g. Gemini API Setup

1. Go to **https://aistudio.google.com**
2. Click **"Get API key"** → **"Create API key"**
3. Copy the key (it starts with `AIza...`)
4. Add it to your `.env` file as `GOOGLE_GEMINI_API_KEY`

> **Important**: If your key contains a `#` character, wrap the value in double quotes in `.env`:
> ```
> GOOGLE_GEMINI_API_KEY="AIzaSy...#rest-of-key"
> ```

---

### h. Environment Variables (.env setup)

Copy the example file and fill in your values:

```bash
cp .env.example .env
```

Your `.env` should look like this:

```env
# Telegram
TELEGRAM_API_ID=12345678
TELEGRAM_API_HASH=abcdef1234567890abcdef1234567890
TELEGRAM_CHANNEL=@your_channel

# Gemini AI
GOOGLE_GEMINI_API_KEY="AIzaSy..."

# Oracle Cloud (for oracle_retry.py — not needed for main pipeline)
OCI_COMPARTMENT_ID=ocid1.tenancy.oc1..xxxxx
OCI_SUBNET_ID=ocid1.subnet.oc1.iad.xxxxx
```

> `OCI_SSH_PUBLIC_KEY` is intentionally **not** stored in `.env` because it reads from your key file. Export it before running `oracle_retry.py`:
> ```bash
> export OCI_SSH_PUBLIC_KEY="$(cat ~/.ssh/id_ed25519.pub)"
> ```

---

### i. Install Dependencies and Run verify.py

```bash
cd ~/telegram-to-youtube
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Then run the verification script to confirm every service is reachable:

```bash
python verify.py
```

Expected output:

```
Verifying services…

  DB           ✅  data/videos.db initialised
  Telegram     ✅  signed in as @yourusername  |  channel: Your Channel Name
  YouTube      ✅  token valid  |  scopes=[...]
  Gemini       ✅  model=gemini-flash-lite-latest  reply='ok'

All services OK — ready to run main.py
```

If any service shows ❌, see the [Troubleshooting](#10-troubleshooting) section.

---

### j. Authorize Telegram Session (one-time)

The first time Telethon connects, it needs your phone number and a confirmation code sent to your Telegram account. Run this once interactively:

```bash
python auth_telegram.py
```

Enter your phone number (with country code, e.g. `+201234567890`), then enter the code Telegram sends you. The session is saved to `data/telegram_session.session` and never needs to be repeated.

---

### k. Running the Pipeline

```bash
source .venv/bin/activate
python main.py
```

The scheduler starts and logs its configured times:

```
Scheduler started — download at 03:00, uploads at [4, 7, 13, 14, 16, 21]
```

It will now run forever, waking up only at the scheduled times. Leave it running in a `screen` or `tmux` session, or deploy it as a systemd service (see [Section 7](#7-deployment-on-oracle-cloud-free-tier)).

---

## 6. Configuration Reference

All settings live in `config.py`. Edit this file directly — no restart required for the next scheduled job.

### Telegram

| Setting | Default | Description |
|---------|---------|-------------|
| `TELEGRAM_API_ID` | from `.env` | Numeric app ID from my.telegram.org |
| `TELEGRAM_API_HASH` | from `.env` | Hex hash from my.telegram.org |
| `TELEGRAM_CHANNEL` | from `.env` | Channel username (e.g. `@memovideos`) or numeric ID |
| `TELEGRAM_SESSION` | `data/telegram_session` | Path to the Telethon session file |

### Daily Limits

| Setting | Default | Description |
|---------|---------|-------------|
| `MAX_DOWNLOADS_PER_DAY` | `10` | Maximum videos downloaded from Telegram per day |
| `MAX_UPLOADS_PER_DAY` | `6` | Maximum videos uploaded to YouTube per day |

### Gemini AI

| Setting | Default | Description |
|---------|---------|-------------|
| `GEMINI_API_KEY` | from `.env` | Google AI Studio API key |
| `GEMINI_MODEL` | `gemini-flash-lite-latest` | Gemini model to use for metadata generation |

### YouTube

| Setting | Default | Description |
|---------|---------|-------------|
| `YOUTUBE_CLIENT_SECRETS` | `credentials/youtube_client_secrets.json` | OAuth client secrets for YouTube |
| `YOUTUBE_TOKEN` | `credentials/youtube_token.json` | Saved OAuth token (auto-refreshed) |
| `YOUTUBE_CATEGORY_ID` | `"22"` | YouTube category ID. 22 = People & Blogs. See [full list](https://developers.google.com/youtube/v3/docs/videoCategories/list) |
| `YOUTUBE_PRIVACY` | `"public"` | Upload visibility: `public`, `private`, or `unlisted` |
| `YOUTUBE_FIXED_TAGS` | See `config.py` | Tags added to every video regardless of content |
| `YOUTUBE_FIXED_HASHTAGS` | See `config.py` | Hashtags always appended to every video |
| `SHORTS_MAX_DURATION` | `60` | Videos at or under this many seconds are treated as YouTube Shorts |

**Hashtag placement rules:**
- **Shorts** (duration ≤ 60s): hashtags appended to the **title** (within 100-char limit)
- **Regular videos** (duration > 60s): hashtags appended to the end of the **description**

### Scheduler

| Setting | Default | Description |
|---------|---------|-------------|
| `SCHEDULER_TIMEZONE` | `Africa/Cairo` | All schedule times are interpreted in this timezone |
| `DOWNLOAD_HOUR` | `3` | Hour (0–23) when the daily download job runs |
| `UPLOAD_HOURS` | `[4, 7, 13, 14, 16, 21]` | List of hours when upload jobs run. One video per slot. |

---

## 7. Deployment on Oracle Cloud Free Tier

Oracle Cloud's Always Free tier includes one **A1.Flex** instance (ARM-based) with up to 4 OCPUs and 24 GB RAM at no cost — more than enough to run this pipeline 24/7.

### 7a. Provision the VM using oracle_retry.py

A1.Flex instances are in high demand and frequently show "Out of host capacity" errors. The included `oracle_retry.py` script retries every 5 minutes across all 3 Ashburn availability domains until one succeeds.

**Setup** (ensure `~/.oci/config` exists with your OCI credentials):

```bash
# Required only for oracle_retry.py — already in .env for the main pipeline:
export OCI_SSH_PUBLIC_KEY="$(cat ~/.ssh/id_ed25519.pub)"

source .venv/bin/activate
python oracle_retry.py
```

The script will:
1. Auto-detect all Ashburn availability domains
2. Find the latest Ubuntu 22.04 ARM64 platform image
3. Try AD-1 → AD-2 → AD-3 every 5 minutes
4. Print the instance OCID and exit when one succeeds

Default instance spec: **1 OCPU / 6 GB RAM / Ubuntu 22.04 ARM64**. Adjust `OCPUS` and `MEMORY_GB` at the top of the script.

**After the VM is ready**, SSH in and clone this repository:

```bash
ssh ubuntu@<instance-public-ip>
git clone https://github.com/your-repo/telegram-to-youtube.git
cd telegram-to-youtube
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Copy your `.env` and `credentials/` folder to the VM:

```bash
# From your local machine:
scp .env ubuntu@<ip>:~/telegram-to-youtube/
scp -r credentials/ ubuntu@<ip>:~/telegram-to-youtube/
```

### 7b. Run as a systemd service

The included `setup_service.sh` script handles everything automatically:

```bash
bash setup_service.sh
```

Or create the service file manually:

```bash
sudo nano /etc/systemd/system/tg2yt.service
```

```ini
[Unit]
Description=Telegram → YouTube pipeline
After=network-online.target
Wants=network-online.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/telegram-to-youtube
ExecStart=/home/ubuntu/telegram-to-youtube/.venv/bin/python main.py
Restart=on-failure
RestartSec=30
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable tg2yt
sudo systemctl start tg2yt
```

Check it is running:

```bash
sudo systemctl status tg2yt
sudo journalctl -u tg2yt -f        # live log tail
```

---

## 8. Scheduler Explained

The pipeline uses `APScheduler` with cron triggers. All times are in **Cairo time** (`Africa/Cairo`, UTC+2). There are two job types:

### Download job

Runs **once per day at 03:00 Cairo time**. Logic:

1. Check how many videos were already downloaded today
2. Calculate remaining slots: `MAX_DOWNLOADS_PER_DAY − already_downloaded`
3. Iterate through the last 200 Telegram messages, skipping any already in the DB
4. Download up to the remaining count, saving to `data/temp/`
5. **For each downloaded file, in the same job**:
   - Call Gemini to generate title, description, tags, and hashtags
   - Save all metadata to SQLite (`status = on_drive`)
6. File stays in `data/temp/` — ready for the upload job to pick up

> `download_job()` handles both downloading **and** metadata generation in one step. By the time it completes, every video is fully staged with title, tags, and hashtags already in the DB.

### Upload jobs

Run **6 times per day** at: `04:00, 07:00, 13:00, 14:00, 16:00, 21:00` (Cairo time)

Each slot uploads **exactly one video**. Logic:

1. Check how many were already uploaded today
2. If the daily cap is reached, skip
3. Fetch the oldest `on_drive` video from the DB
4. Upload directly from `data/temp/` to YouTube with full metadata
5. On success: mark DB record as `uploaded`, delete the local file from `data/temp/`
6. On failure: revert status to `on_drive` so the next slot retries automatically

### Startup catchup

When `main.py` starts, it checks whether any scheduled jobs were missed since midnight (Cairo time) and runs them immediately. This means the pipeline recovers automatically after a reboot or crash without waiting for the next scheduled slot.

### Why this spacing?

- Downloads at **03:00** ensure videos are staged with metadata before the first upload at **04:00**
- Spreading uploads across the day avoids hitting YouTube's daily quota in a burst
- Retries are free: a failed upload will be automatically picked up by the next slot

---

## 9. Database Schema

The SQLite database lives at `data/videos.db`. It has one table: `videos`.

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER PK | Auto-incremented row ID |
| `telegram_message_id` | INTEGER UNIQUE | Telegram message ID — the deduplication key |
| `telegram_channel` | TEXT | Channel username (e.g. `@memovideos`) |
| `original_filename` | TEXT | Filename as received from Telegram |
| `caption` | TEXT | Original Telegram caption (Arabic) |
| `local_path` | TEXT | Path to the file in `data/temp/` (cleared after upload) |
| `duration` | INTEGER | Video duration in seconds (from Telegram metadata) |
| `drive_file_id` | TEXT | Google Drive file ID — only set for legacy records |
| `drive_account` | TEXT | Drive account name — only set for legacy records |
| `youtube_video_id` | TEXT | YouTube video ID after successful upload |
| `youtube_title` | TEXT | Generated Arabic title |
| `youtube_description` | TEXT | Generated Arabic description (2–3 sentences) |
| `youtube_tags` | TEXT | JSON array of Arabic tags (fixed + dynamic) |
| `youtube_hashtags` | TEXT | JSON array of Arabic hashtags (fixed + dynamic) |
| `status` | TEXT | Current pipeline state (see below) |
| `download_date` | TEXT | YYYY-MM-DD — used to enforce daily download cap |
| `upload_date` | TEXT | YYYY-MM-DD — used to enforce daily upload cap |
| `error_message` | TEXT | Last error message if status is `failed` |
| `created_at` | TEXT | Row creation timestamp |
| `updated_at` | TEXT | Auto-updated on every change (via trigger) |

### Status lifecycle

```
pending → downloading → downloaded → on_drive → uploading → uploaded
                                                          ↘ failed → on_drive (auto-retry)
```

| Status | Meaning |
|--------|---------|
| `downloading` | Currently being downloaded from Telegram |
| `downloaded` | Saved to local temp, metadata not yet generated |
| `on_drive` | Metadata generated, file in `data/temp/`, waiting for upload slot |
| `uploading` | Currently being uploaded to YouTube |
| `uploaded` | Live on YouTube, local file deleted |
| `failed` | An error occurred — check `error_message` column |

> **Important**: `upload_job()` only picks up videos with `status = on_drive`. A video stuck in `downloaded` or any other state will not be uploaded until its status is corrected manually.

### Useful queries

```bash
# Open the database
sqlite3 data/videos.db

-- Count by status
SELECT status, COUNT(*) FROM videos GROUP BY status;

-- See the last 10 uploads
SELECT youtube_title, upload_date, youtube_video_id
FROM videos WHERE status = 'uploaded'
ORDER BY upload_date DESC LIMIT 10;

-- See any failed videos and why
SELECT original_filename, error_message FROM videos WHERE status = 'failed';

-- How many videos downloaded today
SELECT COUNT(*) FROM videos WHERE download_date = date('now');

-- Reset a stuck video back to on_drive so it gets retried
UPDATE videos SET status = 'on_drive', error_message = NULL WHERE id = <id>;
```

---

## 10. Troubleshooting

### Telegram

**`SessionPasswordNeededError`**
Your Telegram account has two-factor authentication enabled. Run `auth_telegram.py` in an interactive terminal and enter your 2FA password when prompted.

**`No new videos found`**
All recent messages in the channel (last 200) are already in the database. The channel may not have posted new videos recently, or `MAX_DOWNLOADS_PER_DAY` was already reached today.

**`FloodWaitError`**
Telegram is rate-limiting you. The error message includes how many seconds to wait. The script will retry automatically on the next scheduled run.

---

### YouTube

**`quotaExceeded`**
YouTube's Data API has a daily quota of 10,000 units. One video upload costs ~1,600 units. At 6 uploads/day you use ~9,600 units — just under the limit. If you hit this, reduce `MAX_UPLOADS_PER_DAY` in `config.py` or request a quota increase in Google Cloud Console.

**`The caller does not have permission`**
The YouTube OAuth token doesn't have the `youtube.upload` scope. Delete `credentials/youtube_token.json` and re-run `auth_youtube.py`.

**`Video is a duplicate`**
YouTube detected that the same video was uploaded before (content ID match). The script marks the DB record as `uploaded` anyway since the video is effectively on YouTube.

---

### Gemini

**`429 RESOURCE_EXHAUSTED` with `limit: 0`**
The free tier quota for the selected model is 0 — the model requires billing to be enabled. Switch to `gemini-flash-lite-latest` in `config.py` (this is the model with free-tier access).

**Gemini returns non-JSON / parse failed**
The model occasionally wraps JSON in markdown code fences. The parser strips these automatically. If it still fails, the script falls back to using the filename as the title and fixed tags/hashtags only.

---

### Configuration

**`ModuleNotFoundError: No module named 'pytz'`**
`pytz` was dropped from the virtual environment, likely after a Python version upgrade that invalidated the old `.venv`. Rebuild it:
```bash
rm -rf .venv
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**`AttributeError: module 'config' has no attribute 'YOUTUBE_FIXED_HASHTAGS'`**
`YOUTUBE_FIXED_HASHTAGS` and `SHORTS_MAX_DURATION` are missing from `config.py`. Add them:
```python
YOUTUBE_FIXED_HASHTAGS: list[str] = ["#مسيحي", "#يسوع", "#الكنيسة"]
SHORTS_MAX_DURATION = 60
```

**Videos stuck in `downloaded` status and never uploaded**
`upload_job()` only picks up videos with `status = on_drive`. If metadata generation failed during `download_job()`, the status may not have been advanced. Check `error_message` in the DB, fix the underlying issue (e.g. Gemini quota), then reset:
```sql
UPDATE videos SET status = 'on_drive', error_message = NULL
WHERE status = 'downloaded';
```

**`download_job()` runs but no videos appear in the DB**
Always trigger jobs through `main.py`, not by calling service functions directly. Running `telegram_downloader.run()` directly bypasses the DB cap checks and status updates. Use:
```python
from main import download_job
download_job()
```

---

### General

**`ModuleNotFoundError: No module named 'X'`**
The virtual environment is not active. Run `source .venv/bin/activate` first.

**The scheduler starts but never runs jobs**
Check that your system clock is correct (`date` command). APScheduler uses the configured timezone (`Africa/Cairo`). On a fresh VM: `sudo timedatectl set-timezone UTC` is fine — the scheduler converts internally via `pytz`.

**`data/videos.db` is locked**
Another instance of `main.py` is already running. Find and stop it: `pkill -f main.py`.

---

## 11. Future Improvements

- **Thumbnail generation**: Use Gemini's vision capabilities to auto-generate a custom YouTube thumbnail from a video frame
- **Multi-channel support**: Extend `config.py` to support multiple source Telegram channels with separate YouTube destinations
- **Upload queue prioritization**: Let certain videos (e.g. those with longer captions) skip the queue
- **Telegram bot notifications**: Send a Telegram message to a private chat when each YouTube upload completes, with the video link
- **Retry backoff**: Implement exponential backoff for failed uploads rather than a flat retry at the next scheduled slot
- **Dashboard**: A simple Flask/FastAPI web page showing pipeline stats from the SQLite DB (uploaded count, queue depth, error rate)
- **YouTube analytics feedback**: Pull view counts from the YouTube API after 7 days and log them to the DB for performance tracking
