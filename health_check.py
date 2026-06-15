#!/usr/bin/env python3
"""Health check script — run every 6 hours via cron (see setup_service.sh)."""
import os
import subprocess
import sys

# Resolve project root so this script works when called from cron
_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _ROOT)
os.chdir(_ROOT)

import config
import db.database as database
from utils.email_alert import send_alert
from utils.logger import get_logger

log = get_logger(__name__)


def check_service_active() -> tuple[bool, str]:
    try:
        result = subprocess.run(
            ["systemctl", "is-active", "tg2yt"],
            capture_output=True, text=True, timeout=10,
        )
        active = result.stdout.strip() == "active"
        return active, "OK" if active else f"Service status: {result.stdout.strip()}"
    except Exception as exc:
        return False, f"Could not check service: {exc}"


def check_youtube_token() -> tuple[bool, str]:
    try:
        from google.auth.exceptions import RefreshError
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials

        token_file = config.YOUTUBE_TOKEN
        if not os.path.exists(token_file):
            return False, "YouTube token file missing"

        creds = Credentials.from_authorized_user_file(
            token_file, ["https://www.googleapis.com/auth/youtube"]
        )
        if creds.valid:
            return True, "OK"
        if creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                with open(token_file, "w") as fh:
                    fh.write(creds.to_json())
                return True, "OK (refreshed)"
            except RefreshError as exc:
                if "invalid_grant" in str(exc):
                    return False, "Token expired (invalid_grant) — run auth_youtube.py on laptop"
                return False, f"Token refresh failed: {exc}"
        return False, "Token invalid and cannot be refreshed"
    except Exception as exc:
        return False, f"Could not check token: {exc}"


def check_recent_uploads() -> tuple[bool, str]:
    try:
        count = database.count_uploads_last_24h()
        if count > 0:
            return True, f"{count} upload(s) in last 24h"
        return False, "No videos uploaded in the last 24 hours"
    except Exception as exc:
        return False, f"Could not check uploads: {exc}"


def check_drive_storage() -> tuple[bool, str]:
    try:
        from services.drive_manager import _available_gb, _get_service

        warnings = []
        for account in config.DRIVE_ACCOUNTS:
            service = _get_service(account)
            free_gb = _available_gb(service)
            if free_gb < 10:
                warnings.append(f"{account['name']}: {free_gb:.1f} GB free")

        if warnings:
            return False, "Low storage — " + ", ".join(warnings)
        return True, "OK"
    except Exception as exc:
        return False, f"Could not check Drive storage: {exc}"


def check_stuck_uploading() -> tuple[bool, str]:
    try:
        count = database.count_stuck_uploading()
        if count:
            return False, f"{count} video(s) stuck in 'uploading' for >1 hour"
        return True, "OK"
    except Exception as exc:
        return False, f"Could not check stuck videos: {exc}"


def main() -> None:
    log.info("=== Health check started ===")
    database.init_db()

    checks = [
        ("Service active",   check_service_active),
        ("YouTube token",    check_youtube_token),
        ("Recent uploads",   check_recent_uploads),
        ("Drive storage",    check_drive_storage),
        ("Stuck uploading",  check_stuck_uploading),
    ]

    failures: list[str] = []
    for name, fn in checks:
        ok, msg = fn()
        log.info("[%s] %s: %s", "OK  " if ok else "FAIL", name, msg)
        if not ok:
            failures.append(f"  - {name}: {msg}")

    if failures:
        body = (
            "tg2yt health check detected the following issues:\n\n"
            + "\n".join(failures)
            + "\n\nCheck the service logs for details:\n"
            "  sudo journalctl -u tg2yt -n 100"
        )
        send_alert("ALERT: tg2yt Health Check Failed", body)
        log.warning("Health check FAILED — alert sent")
    else:
        log.info("All health checks passed")

    log.info("=== Health check finished ===")


if __name__ == "__main__":
    main()
