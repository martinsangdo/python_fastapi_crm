"""
public_auth.py
---------------
Authentication for PUBLIC task endpoints (routers/tasks.py) — endpoints
meant to be triggered by an external scheduler (a cron job, Google Cloud
Scheduler, cron-job.org, ...) rather than a logged-in browser user.

These endpoints skip the JWT/RBAC system entirely (there is no human
"logging in") and instead check a single shared secret sent in a header.
This is much simpler than JWT, which is appropriate here: a scheduler does
not have a browser to hold a refresh token, and this is a machine-to-machine
call, not a user session.

Setup:
    Set PUBLIC_TASK_API_KEY in .env to a long random string, e.g.
        python -c "import secrets; print(secrets.token_hex(32))"
    Then have the scheduler send it as a header on every call:
        X-API-Key: <the secret>
"""

import os

from dotenv import load_dotenv
from fastapi import Header, HTTPException, status

# Load the value from the .env file.
load_dotenv()

PUBLIC_TASK_API_KEY = os.getenv("PUBLIC_TASK_API_KEY")


def require_public_api_key(x_api_key: str = Header(default=None, alias="X-API-Key")) -> None:
    """
    FastAPI dependency: reject the request unless X-API-Key matches the
    configured secret.

    Fails CLOSED: if the operator has not set PUBLIC_TASK_API_KEY yet, every
    call is refused (503) rather than silently allowing unauthenticated
    access — a missing key should never mean "wide open".
    """
    if not PUBLIC_TASK_API_KEY:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="PUBLIC_TASK_API_KEY is not configured on the server.",
        )
    if not x_api_key or x_api_key != PUBLIC_TASK_API_KEY:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key.",
        )
