"""
Manual end-to-end test: download 1 video → Drive → Gemini metadata → YouTube (private).
Run once from the project root; does NOT start the scheduler.
"""
import json
import os
from datetime import date

import config
config.YOUTUBE_PRIVACY = "private"   # force private for this test run

import db.database as database
from services import claude_generator, drive_manager, telegram_downloader, youtube_uploader
from utils.logger import get_logger

log = get_logger("test_run")

SEP = "=" * 60


def main():
    os.makedirs(config.TEMP_DOWNLOAD_DIR, exist_ok=True)
    os.makedirs(os.path.dirname(config.DB_PATH), exist_ok=True)
    database.init_db()

    # ── Step 1: Download 1 video from Telegram ────────────────────────────────
    log.info("Step 1 — downloading 1 video from Telegram channel: %s", config.TELEGRAM_CHANNEL)
    videos = telegram_downloader.run(remaining=1)

    if not videos:
        log.error("No new (unseen) videos found in channel. All recent videos may already be in the DB.")
        return

    video = videos[0]
    file_size_mb = os.path.getsize(video["path"]) / (1024 ** 2)
    log.info("Downloaded: %s  (%.1f MB)", video["filename"], file_size_mb)

    # ── Step 2: Generate Arabic metadata with Gemini ──────────────────────────
    log.info("Step 2 — generating Arabic title and tags with Gemini...")
    metadata = claude_generator.generate_metadata(
        video["caption"], video["filename"], video.get("date")
    )

    # ── Step 3: Upload to Drive (auto-selects account with most free space) ───
    log.info("Step 3 — uploading to Drive...")
    file_id, account_name = drive_manager.upload_file(video["path"])

    database.update_video(
        video["db_id"],
        drive_file_id=file_id,
        drive_account=account_name,
        youtube_title=metadata["title"],
        youtube_tags=metadata["tags"],
        status="on_drive",
    )
    os.remove(video["path"])
    log.info("Stored on Drive %s (file_id=%s)", account_name, file_id)

    # ── Step 4: Fetch back from Drive, upload to YouTube as PRIVATE ───────────
    local_path = os.path.join(config.TEMP_DOWNLOAD_DIR, video["filename"])
    log.info("Step 4 — downloading from Drive for YouTube upload...")
    drive_manager.download_file(file_id, account_name, local_path)

    log.info("Step 5 — uploading to YouTube as PRIVATE...")
    tags     = metadata["tags"] if isinstance(metadata["tags"], list) else json.loads(metadata["tags"])
    video_id = youtube_uploader.upload_video(local_path, metadata["title"], tags)

    database.update_video(
        video["db_id"],
        youtube_video_id=video_id,
        status="uploaded",
        upload_date=date.today().isoformat(),
    )

    # ── Step 6: Delete from Drive, clean up local file ────────────────────────
    log.info("Step 6 — cleaning up Drive and temp file...")
    drive_manager.delete_file(file_id, account_name)
    os.remove(local_path)

    # ── Results ───────────────────────────────────────────────────────────────
    print(f"\n{SEP}")
    print("TEST COMPLETE")
    print(SEP)
    print(f"YouTube Video ID : {video_id}")
    print(f"YouTube URL      : https://youtu.be/{video_id}")
    print(f"Privacy          : PRIVATE")
    print(f"Title            : {metadata['title']}")
    print(f"Tags ({len(tags):2d})         : {', '.join(tags)}")
    print(f"Drive account    : {account_name}")
    print(f"File size        : {file_size_mb:.1f} MB")
    print(f"Post date        : {video.get('date')}")
    print(f"DB record ID     : {video['db_id']}")
    print(SEP)


if __name__ == "__main__":
    main()
