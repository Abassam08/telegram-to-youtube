import asyncio
import os
from typing import List, Dict

from telethon import TelegramClient
from telethon.tl.types import (
    DocumentAttributeFilename,
    DocumentAttributeVideo,
    MessageMediaDocument,
)

import config
from db import database as db
from utils.logger import get_logger

log = get_logger(__name__)


_THUMBNAIL_DIR = "data/thumbnails"


async def _download_videos(
    client: TelegramClient, remaining: int
) -> List[Dict]:
    os.makedirs(config.TEMP_DOWNLOAD_DIR, exist_ok=True)
    os.makedirs(_THUMBNAIL_DIR, exist_ok=True)
    downloaded: List[Dict] = []

    async for message in client.iter_messages(config.TELEGRAM_CHANNEL, limit=200):
        if remaining <= 0:
            break

        # only video documents
        if not message.media or not isinstance(message.media, MessageMediaDocument):
            continue
        doc = message.media.document
        if not doc.mime_type.startswith("video/"):
            continue

        if db.video_exists(message.id):
            log.debug("Skipping already-seen message %s", message.id)
            continue

        # derive filename and duration from document attributes
        filename = f"tg_{message.id}.mp4"
        duration = None
        for attr in doc.attributes:
            if isinstance(attr, DocumentAttributeFilename):
                filename = attr.file_name
            elif isinstance(attr, DocumentAttributeVideo):
                duration = attr.duration

        caption   = message.text or ""
        post_date = message.date.strftime("%Y-%m-%d") if message.date else None
        video_id  = db.insert_video(
            message.id, config.TELEGRAM_CHANNEL, filename, caption
        )

        local_path = os.path.join(config.TEMP_DOWNLOAD_DIR, filename)
        log.info("Downloading message %s → %s", message.id, local_path)
        try:
            await client.download_media(message, file=local_path)

            # Download thumbnail if the video document has one
            thumbnail_path = None
            thumbs = getattr(doc, "thumbs", None)
            if thumbs:
                thumb_dest = os.path.join(_THUMBNAIL_DIR, f"{video_id}.jpg")
                try:
                    await client.download_media(
                        message.media.document.thumbs[-1], file=thumb_dest
                    )
                    thumbnail_path = thumb_dest
                    log.info("Thumbnail saved for video %d → %s", video_id, thumb_dest)
                except Exception as exc:
                    log.warning("Thumbnail download failed for video %d: %s", video_id, exc)

            db.update_video(
                video_id,
                local_path=local_path,
                status="downloaded",
                thumbnail_path=thumbnail_path,
            )
            downloaded.append(
                {
                    "db_id":          video_id,
                    "filename":       filename,
                    "caption":        caption,
                    "date":           post_date,
                    "duration":       duration,
                    "path":           local_path,
                    "thumbnail_path": thumbnail_path,
                }
            )
            remaining -= 1
            log.info("Downloaded %s/%s", len(downloaded), config.MAX_DOWNLOADS_PER_DAY)
        except Exception as exc:
            log.error("Failed to download message %s: %s", message.id, exc)
            db.update_video(video_id, status="failed", error_message=str(exc))

    return downloaded


def run(remaining: int) -> List[Dict]:
    """Synchronous entry-point: downloads up to `remaining` new videos."""

    async def _main() -> List[Dict]:
        async with TelegramClient(
            config.TELEGRAM_SESSION,
            config.TELEGRAM_API_ID,
            config.TELEGRAM_API_HASH,
        ) as client:
            return await _download_videos(client, remaining)

    return asyncio.run(_main())
