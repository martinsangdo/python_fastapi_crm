"""
public_auth.py
----------------
Authentication for PUBLIC API endpoints — ones meant to be called by a
machine (an external scheduler / cron job), not a logged-in browser user.

These endpoints accept no JWT. Instead the caller must send a shared secret
in the "X-API-Key" header, matching PUBLIC_TASK_API_KEY in .env. Generate one
with:  python -c "import secrets; print(secrets.token_hex(32))"
"""

import os
import secrets

from dotenv import load_dotenv
from fastapi import Header, HTTPException, status

load_dotenv()


def require_public_api_key(x_api_key: str = Header(...)) -> None:
    """
    A FastAPI dependency that only lets a request through if it carries the
    correct "X-API-Key" header.

    Usage inside a router:

        @router.post("/api/public/tasks/...", dependencies=[Depends(require_public_api_key)])
        def do_the_task(...):
            ...
    """
    expected_key = os.getenv("PUBLIC_TASK_API_KEY")
    if not expected_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="This public API is not configured (missing PUBLIC_TASK_API_KEY).",
        )

    # compare_digest instead of "==" so the check takes the same time whether
    # the key is right or wrong — that avoids leaking the secret one
    # character at a time through response-timing differences.
    if not secrets.compare_digest(x_api_key, expected_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key.",
        )
