import json
import sqlite3
from datetime import date
from typing import Any, Dict, List, Optional

import config
from utils.logger import get_logger

log = get_logger(__name__)


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS videos (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_message_id INTEGER UNIQUE NOT NULL,
                telegram_channel    TEXT    NOT NULL,
                original_filename   TEXT,
                caption             TEXT,
                local_path          TEXT,
                drive_file_id       TEXT,
                drive_account       TEXT,
                youtube_video_id    TEXT,
                youtube_title       TEXT,
                youtube_tags        TEXT,       -- JSON array
                status              TEXT    NOT NULL DEFAULT 'pending',
                -- pending | downloading | downloaded | on_drive | uploading | uploaded | failed
                download_date       TEXT,       -- YYYY-MM-DD
                upload_date         TEXT,       -- YYYY-MM-DD
                error_message       TEXT,
                created_at          TEXT DEFAULT (datetime('now')),
                updated_at          TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS videos_set_updated_at
            AFTER UPDATE ON videos
            BEGIN
                UPDATE videos SET updated_at = datetime('now') WHERE id = NEW.id;
            END
        """)
    log.info("Database initialised at %s", config.DB_PATH)


def video_exists(message_id: int) -> bool:
    with _conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM videos WHERE telegram_message_id = ?", (message_id,)
        ).fetchone()
    return row is not None


def insert_video(
    message_id: int,
    channel: str,
    filename: str,
    caption: str,
) -> int:
    with _conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO videos
                (telegram_message_id, telegram_channel, original_filename,
                 caption, status, download_date)
            VALUES (?, ?, ?, ?, 'downloading', ?)
            """,
            (message_id, channel, filename, caption, date.today().isoformat()),
        )
        return cur.lastrowid  # type: ignore[return-value]


def update_video(video_id: int, **kwargs: Any) -> None:
    if not kwargs:
        return
    if "youtube_tags" in kwargs and isinstance(kwargs["youtube_tags"], list):
        kwargs["youtube_tags"] = json.dumps(kwargs["youtube_tags"], ensure_ascii=False)
    sets   = ", ".join(f"{k} = ?" for k in kwargs)
    values = list(kwargs.values()) + [video_id]
    with _conn() as conn:
        conn.execute(f"UPDATE videos SET {sets} WHERE id = ?", values)


def count_downloads_today() -> int:
    with _conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM videos WHERE download_date = ?",
            (date.today().isoformat(),),
        ).fetchone()
    return row[0]


def count_uploads_today() -> int:
    with _conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM videos WHERE upload_date = ? AND status = 'uploaded'",
            (date.today().isoformat(),),
        ).fetchone()
    return row[0]


def get_pending_uploads(limit: int = 5) -> List[Dict[str, Any]]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM videos WHERE status = 'on_drive' ORDER BY id LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_video(video_id: int) -> Optional[Dict[str, Any]]:
    with _conn() as conn:
        row = conn.execute("SELECT * FROM videos WHERE id = ?", (video_id,)).fetchone()
    return dict(row) if row else None
