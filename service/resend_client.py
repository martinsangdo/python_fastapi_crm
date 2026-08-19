"""
resend_client.py
------------------
Thin wrapper around Resend (https://resend.com) for sending transactional
emails — used by the daily summary email job. Requires RESEND_API_KEY (and
optionally RESEND_FROM_EMAIL) in .env.
"""

import os

from dotenv import load_dotenv

load_dotenv()


class EmailNotConfiguredError(Exception):
    """Raised when RESEND_API_KEY is missing, so callers can return a clean error."""


def send_email(*, to: str, subject: str, html: str) -> str:
    """
    Send one HTML email via Resend. Returns Resend's id for the sent email.

    Note: with the default "onboarding@resend.dev" sender (no verified
    domain), Resend only delivers to the address you signed up to Resend
    with — see the comment next to RESEND_FROM_EMAIL in .env.
    """
    api_key = os.getenv("RESEND_API_KEY")
    if not api_key:
        raise EmailNotConfiguredError("RESEND_API_KEY is not set.")
    from_email = os.getenv("RESEND_FROM_EMAIL", "onboarding@resend.dev")

    import resend  # imported lazily so the package is only needed if used

    resend.api_key = api_key
    result = resend.Emails.send(
        {
            "from": from_email,
            "to": [to],
            "subject": subject,
            "html": html,
        }
    )
    return result.get("id")
