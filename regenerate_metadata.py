"""One-time script: regenerate youtube_description, youtube_tags, and
youtube_hashtags for all videos with status='on_drive'.

Usage:
    python3 regenerate_metadata.py
"""

import sqlite3
import time

import config
from db.database import update_video
from services.claude_generator import generate_metadata
from utils.logger import get_logger

log = get_logger(__name__)


def _get_on_drive_videos():
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, caption, original_filename, download_date "
        "FROM videos WHERE status = 'on_drive' ORDER BY id"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def main():
    videos = _get_on_drive_videos()
    total = len(videos)
    print(f"Found {total} video(s) with status='on_drive'.")

    for i, video in enumerate(videos, 1):
        vid_id   = video["id"]
        caption  = video["caption"] or ""
        filename = video["original_filename"] or ""
        date     = video["download_date"]

        log.info("Regenerating metadata for video id=%d (%d/%d)", vid_id, i, total)
        print(f"  [{i}/{total}] id={vid_id}  filename={filename!r}")

        metadata = generate_metadata(caption=caption, filename=filename, date=date)

        update_video(
            vid_id,
            youtube_description=metadata["description"],
            youtube_tags=metadata["tags"],
            youtube_hashtags=metadata["hashtags"],
        )

        if i < total:
            time.sleep(2)

    print(f"\nDone. {total} video(s) regenerated.")


if __name__ == "__main__":
    main()
