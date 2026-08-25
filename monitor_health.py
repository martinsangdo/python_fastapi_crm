"""Send an email alert if the local health endpoint fails twice in a row.

Run this script periodically (for example, with cron):
    python3 monitor_health.py

Required .env settings:
    RESEND_API_KEY=...
    CUSTOMER_CARE_NOTIFY_EMAIL=alerts@example.com

Optional settings:
    RESEND_FROM_EMAIL=onboarding@resend.dev
    HEALTH_CHECK_URL=http://127.0.0.1:8000/api/health
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

from service.resend_client import send_email


PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(PROJECT_ROOT / ".env")

HEALTH_CHECK_URL = os.getenv(
    "HEALTH_CHECK_URL", "http://127.0.0.1:8000/api/health"
)
RETRY_DELAY_SECONDS = 30
REQUEST_TIMEOUT_SECONDS = 10


def check_health() -> tuple[bool, str]:
    """Return whether a retry/alert is needed, and a message for the alert."""
    try:
        response = httpx.get(HEALTH_CHECK_URL, timeout=REQUEST_TIMEOUT_SECONDS)
    except httpx.RequestError as exc:
        return True, f"Không thể kết nối tới health API: {exc}"

    if response.status_code == 200:
        return False, ""
    if response.status_code == 400:
        return True, "Health API trả về HTTP 400."

    # Theo yêu cầu, chỉ HTTP 400 và lỗi kết nối mới kích hoạt cảnh báo.
    return False, ""


def send_alert(reason: str) -> None:
    """Send the health alert to the recipient configured in .env."""
    recipient = os.getenv("CUSTOMER_CARE_NOTIFY_EMAIL")
    if not recipient:
        raise RuntimeError("CUSTOMER_CARE_NOTIFY_EMAIL is not set in .env.")

    send_email(
        to=recipient,
        subject="[Cảnh báo] Health API không hoạt động",
        html=(
            "<p>Health API vẫn gặp sự cố sau hai lần kiểm tra.</p>"
            f"<p><strong>URL:</strong> {HEALTH_CHECK_URL}</p>"
            f"<p><strong>Chi tiết:</strong> {reason}</p>"
        ),
    )


def main() -> None:
    first_check_failed, _ = check_health()
    if not first_check_failed:
        return

    time.sleep(RETRY_DELAY_SECONDS)
    second_check_failed, reason = check_health()
    if not second_check_failed:
        return

    send_alert(reason)


if __name__ == "__main__":
    main()
