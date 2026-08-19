"""
ntfy_service.py
------------------
Sends push notifications through ntfy (https://ntfy.sh) — a simple pub/sub
service: publish a message to a topic, and every device subscribed to that
topic (via the ntfy mobile app, or a browser) gets a push notification. No
account or API key needed on the public ntfy.sh server — the topic name
itself acts as a shared secret, so keep it long/random-looking.

Used by the public "latest customer" notify task
(service/customer_care_service.py's notify_latest_customer_via_ntfy) to
alert the sales team's phones as soon as a new customer is added.

--------------------------------------------------------------------------
ONE-TIME SETUP (ntfy)
--------------------------------------------------------------------------
1. Install the ntfy app (iOS / Android) or open https://ntfy.sh in a browser.
2. Subscribe to the topic named in NTFY_TOPIC (.env). It does not need to
   be created ahead of time — subscribing and publishing both just work.
--------------------------------------------------------------------------
"""

import os
from typing import Optional

import httpx
from dotenv import load_dotenv

# Load NTFY_SERVER / NTFY_TOPIC from .env.
load_dotenv()

NTFY_SERVER = os.getenv("NTFY_SERVER", "https://ntfy.sh").rstrip("/")
NTFY_TOPIC = os.getenv("NTFY_TOPIC", "my-crm-new-customer-7839322345")


class NtfyConfigError(Exception):
    """
    Raised when the ntfy integration isn't set up correctly: the topic is
    missing, OR the ntfy server could not be reached / rejected the
    request. Callers (routers/tasks.py) map this to a 503 with the message
    as-is.
    """


def send_notification(*, message: str, title: Optional[str] = None) -> dict:
    """
    Publish one push notification to NTFY_TOPIC and return ntfy's JSON
    response. Uses ntfy's JSON publish endpoint (rather than the header-based
    one) so titles/messages with non-ASCII text (e.g. Vietnamese names) are
    sent correctly.

    Raises NtfyConfigError if NTFY_TOPIC is unset, the ntfy server cannot be
    reached, or it rejects the request.
    """
    if not NTFY_TOPIC:
        raise NtfyConfigError("NTFY_TOPIC is not set in .env.")

    payload = {"topic": NTFY_TOPIC, "message": message}
    if title:
        payload["title"] = title

    try:
        response = httpx.post(f"{NTFY_SERVER}/", json=payload, timeout=10)
    except httpx.HTTPError as error:
        raise NtfyConfigError(f"Could not reach the ntfy server: {error}") from error

    if response.status_code >= 400:
        raise NtfyConfigError(
            f"ntfy request failed ({response.status_code}): {response.text}"
        )
    return response.json()
