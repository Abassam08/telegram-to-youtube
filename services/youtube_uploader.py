import os
from typing import List, Optional

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

import config
from utils.logger import get_logger

log = get_logger(__name__)

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


class YouTubeTokenExpiredError(Exception):
    pass


def _handle_token_expired() -> None:
    import db.database as database
    from utils.email_alert import send_alert

    reset_ids = database.reset_uploading_to_on_drive()
    if reset_ids:
        log.info("Reset %d video(s) from uploading → on_drive: %s", len(reset_ids), reset_ids)

    log.critical(
        "YOUTUBE TOKEN EXPIRED — run auth_youtube.py on your laptop to renew the token"
    )
    send_alert(
        "ALERT: YouTube Token Expired",
        "The YouTube OAuth token has expired (invalid_grant).\n\n"
        "Action required: run auth_youtube.py on your laptop, then copy the new\n"
        f"token file to the server at: {config.YOUTUBE_TOKEN}\n\n"
        "Affected videos have been reset to on_drive status and will retry automatically.",
    )


def _get_service():
    token_file = config.YOUTUBE_TOKEN
    creds = None

    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except RefreshError as exc:
                if "invalid_grant" in str(exc):
                    _handle_token_expired()
                    raise YouTubeTokenExpiredError("YouTube token expired") from exc
                raise
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
) -> tuple[str, str]:
    """Append hashtags to the description."""
    if not hashtags:
        return title, description
    final_desc = description.rstrip() + "\n\n" + " ".join(hashtags)
    return title, final_desc


def upload_video(
    local_path: str,
    title: str,
    tags: List[str],
    description: str = "",
    hashtags: Optional[List[str]] = None,
) -> str:
    """Upload a video file to YouTube. Returns the video_id on success.
    Raises on API / quota errors so the caller can mark the job for retry.
    """
    final_title, final_description = _apply_hashtags(
        title, description, hashtags or []
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
