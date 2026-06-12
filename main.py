import json
import os
from datetime import date

import pytz
from apscheduler.schedulers.blocking import BlockingScheduler

import config
import db.database as database
from services import (
    claude_generator,
    drive_manager,
    telegram_downloader,
    thumbnail_generator,
    youtube_uploader,
)
from services.youtube_uploader import YouTubeTokenExpiredError
from utils.logger import get_logger

log = get_logger(__name__)


def download_job() -> None:
    log.info("=== Download job started ===")

    already    = database.count_downloads_today()
    remaining  = config.MAX_DOWNLOADS_PER_DAY - already
    if remaining <= 0:
        log.info("Daily download cap reached (%d), skipping", config.MAX_DOWNLOADS_PER_DAY)
        return

    log.info("Downloading up to %d new video(s)", remaining)
    downloaded = telegram_downloader.run(remaining)
    log.info("Downloaded %d video(s) from Telegram", len(downloaded))

    for video in downloaded:
        try:
            # 1. Generate Arabic title + tags via Gemini
            metadata = claude_generator.generate_metadata(
                video["caption"], video["filename"], video.get("date")
            )

            # 2. Mark ready for YouTube upload — file stays in data/temp/
            database.update_video(
                video["db_id"],
                duration=video.get("duration"),
                youtube_title=metadata["title"],
                youtube_description=metadata.get("description", ""),
                youtube_tags=metadata["tags"],
                youtube_hashtags=metadata.get("hashtags", []),
                status="on_drive",
            )

            log.info("Video %d staged for upload: %s", video["db_id"], metadata["title"])

        except Exception as exc:
            log.error("Error processing video %d: %s", video["db_id"], exc)
            database.update_video(
                video["db_id"], status="failed", error_message=str(exc)
            )

    log.info("=== Download job finished ===")


def upload_job() -> None:
    log.info("=== Upload job started ===")

    already   = database.count_uploads_today()
    remaining = config.MAX_UPLOADS_PER_DAY - already
    if remaining <= 0:
        log.info("Daily upload cap reached (%d), skipping", config.MAX_UPLOADS_PER_DAY)
        return

    # one upload per scheduled run keeps videos spread across the day
    pending = database.get_pending_uploads(limit=1)
    if not pending:
        log.info("No videos pending upload")
        return

    video         = pending[0]
    drive_file_id = video["drive_file_id"] if video["drive_file_id"] else ""

    try:
        database.update_video(video["id"], status="uploading")

        if drive_file_id:
            # backward compat: record was previously uploaded to Drive
            local_path = os.path.join(config.TEMP_DOWNLOAD_DIR, video["original_filename"])
            log.info("Fetching from Drive: %s", drive_file_id)
            drive_manager.download_file(drive_file_id, video["drive_account"], local_path)
        else:
            # new path: file is already on disk in data/temp/
            local_path = video["local_path"] or os.path.join(
                config.TEMP_DOWNLOAD_DIR, video["original_filename"]
            )
            if not os.path.exists(local_path):
                raise FileNotFoundError(f"Local file not found: {local_path}")
            log.info("Uploading directly from local file: %s", local_path)

        tags        = json.loads(video["youtube_tags"]     or "[]")
        hashtags    = json.loads(video["youtube_hashtags"] or "[]")
        description = video.get("youtube_description") or ""
        video_id    = youtube_uploader.upload_video(
            local_path, video["youtube_title"], tags,
            description, hashtags,
        )

        database.update_video(
            video["id"],
            youtube_video_id=video_id,
            status="uploaded",
            upload_date=date.today().isoformat(),
        )

        # Thumbnail: prefer the one downloaded from Telegram; fall back to
        # generator for long-form videos only; skip entirely for Shorts.
        duration       = video.get("duration") or 0
        tg_thumb       = video.get("thumbnail_path") or ""
        thumbnail_path = None
        if tg_thumb and os.path.exists(tg_thumb):
            thumbnail_path = tg_thumb
        elif duration > 60:
            try:
                thumbnail_path = thumbnail_generator.generate(
                    local_path, video["youtube_title"], video["id"]
                )
            except Exception as exc:
                log.error(
                    "Thumbnail generation failed for video %d: %s",
                    video["id"], exc,
                )
        if thumbnail_path:
            try:
                youtube_uploader.set_thumbnail(video_id, thumbnail_path)
            except Exception as exc:
                log.error(
                    "Thumbnail upload failed for video %d: %s",
                    video["id"], exc,
                )

        if drive_file_id:
            drive_manager.delete_file(drive_file_id, video["drive_account"])
            log.info("Video %d uploaded and cleaned up from Drive", video["id"])
        else:
            os.remove(local_path)
            log.info("Video %d uploaded and local file removed", video["id"])

    except YouTubeTokenExpiredError:
        # youtube_uploader already logged, sent email, and reset statuses
        log.error("YouTube token expired — upload job aborted, waiting for token renewal")

    except Exception as exc:
        log.error("Upload failed for video %d: %s", video["id"], exc)

        current      = database.get_video(video["id"])
        retry_count  = (current.get("retry_count") or 0) + 1

        if retry_count >= 3:
            log.warning(
                "Video %d failed %d times — marking as failed", video["id"], retry_count
            )
            database.update_video(
                video["id"],
                status="failed",
                retry_count=retry_count,
                error_message=str(exc),
            )
        else:
            log.info(
                "Video %d failed (attempt %d/3) — will retry", video["id"], retry_count
            )
            database.update_video(
                video["id"],
                status="on_drive",
                retry_count=retry_count,
                error_message=str(exc),
            )

        # if we fetched from Drive, delete the local temp copy we created
        if drive_file_id:
            local_path = os.path.join(config.TEMP_DOWNLOAD_DIR, video["original_filename"])
            if os.path.exists(local_path):
                os.remove(local_path)

    log.info("=== Upload job finished ===")


def _cairo_now():
    """Current time in Cairo (Africa/Cairo, UTC+2)."""
    return __import__("datetime").datetime.now(pytz.timezone(config.SCHEDULER_TIMEZONE))


def startup_catchup() -> None:
    """Run any jobs that were scheduled for today (Cairo time) but missed before startup."""
    cairo_now  = _cairo_now()
    now_hour   = cairo_now.hour

    log.info(
        "Startup catchup check — Cairo time: %s",
        cairo_now.strftime("%Y-%m-%d %H:%M %Z"),
    )

    # ── Download catchup ──────────────────────────────────────────────────────
    # Missed if: the download hour has passed AND nothing was downloaded today
    if now_hour > config.DOWNLOAD_HOUR and database.count_downloads_today() == 0:
        log.info(
            "Catchup: download slot (%02d:00 Cairo) was missed — running now",
            config.DOWNLOAD_HOUR,
        )
        download_job()

    # ── Upload catchup ────────────────────────────────────────────────────────
    # Count upload slots whose HH:MM has already passed today in Cairo time
    now_hhmm      = (cairo_now.hour, cairo_now.minute)
    missed_slots  = sum(
        1 for t in config.UPLOAD_TIMES
        if tuple(int(x) for x in t.split(":")) < now_hhmm
    )
    uploads_done  = database.count_uploads_today()
    pending_count = len(database.get_pending_uploads(limit=1))

    if missed_slots > uploads_done and pending_count > 0:
        log.info(
            "Catchup: %d upload slot(s) passed today, only %d completed, "
            "%d pending — running upload job now",
            missed_slots, uploads_done, pending_count,
        )
        upload_job()


def main() -> None:
    os.makedirs(config.TEMP_DOWNLOAD_DIR, exist_ok=True)
    os.makedirs(os.path.dirname(config.DB_PATH), exist_ok=True)
    database.init_db()

    tz = pytz.timezone(config.SCHEDULER_TIMEZONE)

    startup_catchup()

    scheduler = BlockingScheduler(timezone=tz)

    scheduler.add_job(download_job, "cron", hour=config.DOWNLOAD_HOUR, minute=0)
    for t in config.UPLOAD_TIMES:
        h, m = (int(x) for x in t.split(":"))
        scheduler.add_job(upload_job, "cron", hour=h, minute=m)

    log.info(
        "Scheduler started (timezone=%s) — download at %02d:00, uploads at %s",
        config.SCHEDULER_TIMEZONE,
        config.DOWNLOAD_HOUR,
        config.UPLOAD_TIMES,
    )
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("Scheduler stopped")


if __name__ == "__main__":
    main()
