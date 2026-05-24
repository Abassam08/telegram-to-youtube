import io
import os
from typing import Dict, Tuple

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload

import config
from utils.logger import get_logger

log = get_logger(__name__)

SCOPES = ["https://www.googleapis.com/auth/drive"]


def _get_service(account: Dict):
    token_file = account["token_file"]
    creds = None

    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                config.DRIVE_CLIENT_SECRETS, SCOPES
            )
            creds = flow.run_local_server(port=0)
        os.makedirs(os.path.dirname(token_file), exist_ok=True)
        with open(token_file, "w") as fh:
            fh.write(creds.to_json())

    return build("drive", "v3", credentials=creds)


def _get_or_create_folder(service, folder_name: str) -> str:
    results = service.files().list(
        q=(
            f"name='{folder_name}' "
            "and mimeType='application/vnd.google-apps.folder' "
            "and trashed=false"
        ),
        fields="files(id)",
    ).execute()
    files = results.get("files", [])
    if files:
        return files[0]["id"]

    meta   = {"name": folder_name, "mimeType": "application/vnd.google-apps.folder"}
    folder = service.files().create(body=meta, fields="id").execute()
    return folder["id"]


def _available_gb(service) -> float:
    about = service.about().get(fields="storageQuota").execute()
    quota = about.get("storageQuota", {})
    total = int(quota.get("limit", 0))
    used  = int(quota.get("usage", 0))
    return (total - used) / (1024 ** 3)


def upload_file(local_path: str) -> Tuple[str, str]:
    """Upload to the first account with sufficient space.

    Returns (drive_file_id, account_name).
    """
    file_size_gb = os.path.getsize(local_path) / (1024 ** 3)

    for account in config.DRIVE_ACCOUNTS:
        service   = _get_service(account)
        available = _available_gb(service)
        log.info("Drive %s: %.2f GB free", account["name"], available)

        if available < file_size_gb + 0.5:  # 0.5 GB safety buffer
            log.warning(
                "Drive %s: insufficient space (need %.2f GB), trying next",
                account["name"],
                file_size_gb,
            )
            continue

        folder_id = _get_or_create_folder(service, config.DRIVE_FOLDER_NAME)
        media     = MediaFileUpload(local_path, resumable=True)
        meta      = {"name": os.path.basename(local_path), "parents": [folder_id]}
        result    = service.files().create(
            body=meta, media_body=media, fields="id"
        ).execute()

        log.info(
            "Uploaded %s → Drive %s (file_id=%s)",
            local_path,
            account["name"],
            result["id"],
        )
        return result["id"], account["name"]

    raise RuntimeError("No Drive account has sufficient free space")


def download_file(file_id: str, account_name: str, dest_path: str) -> None:
    account = next(a for a in config.DRIVE_ACCOUNTS if a["name"] == account_name)
    service = _get_service(account)
    request = service.files().get_media(fileId=file_id)

    os.makedirs(os.path.dirname(dest_path) or ".", exist_ok=True)
    with open(dest_path, "wb") as fh:
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()
            if status:
                log.info("Drive download progress: %d%%", int(status.progress() * 100))


def delete_file(file_id: str, account_name: str) -> None:
    account = next(a for a in config.DRIVE_ACCOUNTS if a["name"] == account_name)
    service = _get_service(account)
    service.files().delete(fileId=file_id).execute()
    log.info("Deleted Drive file %s from %s", file_id, account_name)
