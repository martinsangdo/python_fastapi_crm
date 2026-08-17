"""
email_service.py
------------------
Sends transactional email through the Resend API (https://resend.com) — used
by the public "new customers today" summary email task
(service/customer_care_service.py's check_new_customers_and_email).

--------------------------------------------------------------------------
ONE-TIME SETUP (Resend)
--------------------------------------------------------------------------
1. Create a free account at https://resend.com and copy an API key
   (Dashboard -> API Keys) into RESEND_API_KEY in .env.
2. Set RESEND_FROM_EMAIL in .env. Without your own verified sending domain,
   Resend's shared test address "onboarding@resend.dev" works out of the
   box, but can only deliver to the email address you signed up to Resend
   with. To send to any other Gmail address, verify a domain first
   (Dashboard -> Domains) and use an address on that domain instead.
3. Set CUSTOMER_CARE_NOTIFY_EMAIL in .env to the Gmail address that should
   receive the daily summary.
--------------------------------------------------------------------------
"""

import os

import httpx
from dotenv import load_dotenv

# Load RESEND_API_KEY / RESEND_FROM_EMAIL from .env.
load_dotenv()

RESEND_API_URL = "https://api.resend.com/emails"
RESEND_API_KEY = os.getenv("RESEND_API_KEY")
RESEND_FROM_EMAIL = os.getenv("RESEND_FROM_EMAIL", "onboarding@resend.dev")


class EmailConfigError(Exception):
    """
    Raised when the Resend integration isn't set up correctly: the API key
    is missing, OR Resend rejected the request (e.g. an unverified sender
    domain). Callers (routers/tasks.py) map this to a 503 with the message
    as-is.
    """


def send_email(*, to: str, subject: str, html: str) -> dict:
    """
    Send one email through Resend and return its JSON response (a dict that
    includes "id"). Raises EmailConfigError if RESEND_API_KEY is unset, the
    Resend API cannot be reached, or Resend rejects the request.
    """
    if not RESEND_API_KEY:
        raise EmailConfigError("RESEND_API_KEY is not set in .env.")

    try:
        response = httpx.post(
            RESEND_API_URL,
            headers={"Authorization": f"Bearer {RESEND_API_KEY}"},
            json={"from": RESEND_FROM_EMAIL, "to": [to], "subject": subject, "html": html},
            timeout=10,
        )
    except httpx.HTTPError as error:
        raise EmailConfigError(f"Could not reach the Resend API: {error}") from error

    if response.status_code >= 400:
        raise EmailConfigError(
            f"Resend API request failed ({response.status_code}): {response.text}"
        )
    return response.json()
