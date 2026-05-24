import os
from typing import List, Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

import config
from utils.logger import get_logger

log = get_logger(__name__)

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def _get_service():
    token_file = config.YOUTUBE_TOKEN
    creds = None

    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                config.YOUTUBE_CLIENT_SECRETS, SCOPES
            )
            creds = flow.run_local_server(port=0)
        os.makedirs(os.path.dirname(token_file), exist_ok=True)
        with open(token_file, "w") as fh:
            fh.write(creds.to_json())

    return build("youtube", "v3", credentials=creds)


def _apply_hashtags(
    title: str,
    description: str,
    hashtags: List[str],
    duration: Optional[int],
) -> tuple[str, str]:
    """Append hashtags to title (Shorts) or description (regular video)."""
    if not hashtags:
        return title, description

    hashtag_str = " ".join(hashtags)
    is_short    = duration is not None and duration <= config.SHORTS_MAX_DURATION

    if is_short:
        # keep total title within 100 chars
        max_base = 100 - len(hashtag_str) - 1
        final_title = f"{title[:max_base].rstrip()} {hashtag_str}"
        return final_title, description
    else:
        final_desc = description.rstrip() + "\n\n" + hashtag_str
        return title, final_desc


def upload_video(
    local_path: str,
    title: str,
    tags: List[str],
    description: str = "",
    hashtags: Optional[List[str]] = None,
    duration: Optional[int] = None,
) -> str:
    """Upload a video file to YouTube.

    Hashtags are appended to the title for Shorts (duration <= SHORTS_MAX_DURATION)
    or to the description for regular videos.

    Returns the YouTube video_id on success.
    Raises on API / quota errors so the caller can mark the job for retry.
    """
    final_title, final_description = _apply_hashtags(
        title, description, hashtags or [], duration
    )
    service = _get_service()

    body = {
        "snippet": {
            "title":       final_title[:100],
            "description": final_description,
            "tags":        tags,
            "categoryId":  config.YOUTUBE_CATEGORY_ID,
        },
        "status": {
            "privacyStatus": config.YOUTUBE_PRIVACY,
        },
    }

    # chunksize=-1 → single request for small files; resumable handles large ones
    media   = MediaFileUpload(local_path, chunksize=-1, resumable=True)
    request = service.videos().insert(
        part="snippet,status", body=body, media_body=media
    )

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            log.info("YouTube upload progress: %d%%", int(status.progress() * 100))

    video_id = response["id"]
    log.info("Uploaded to YouTube: https://youtu.be/%s  title=%s", video_id, title)
    return video_id
