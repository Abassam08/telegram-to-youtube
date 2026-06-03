import smtplib
from email.mime.text import MIMEText

import config
from utils.logger import get_logger

log = get_logger(__name__)


def send_alert(subject: str, body: str) -> None:
    if not config.GMAIL_APP_PASSWORD or not config.ALERT_EMAIL:
        log.warning("Email alert skipped — ALERT_EMAIL or GMAIL_APP_PASSWORD not set")
        return
    try:
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"]    = config.ALERT_EMAIL
        msg["To"]      = config.ALERT_EMAIL

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(config.ALERT_EMAIL, config.GMAIL_APP_PASSWORD)
            smtp.send_message(msg)

        log.info("Alert email sent: %s", subject)
    except Exception as exc:
        log.error("Failed to send alert email: %s", exc)
