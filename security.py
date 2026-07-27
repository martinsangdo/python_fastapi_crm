"""
security.py
-----------
The low-level security helpers used by the authentication module.

Two jobs live here:
1. Password hashing  -> turn a plain password into a safe BCRYPT hash, and
   later check a login attempt against that hash.
2. JSON Web Tokens (JWT) -> create signed "access" and "refresh" tokens and
   read them back safely.

Nothing here knows about the database or FastAPI. It only does the math, so
it is easy to read and to reuse.
"""

import os
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from dotenv import load_dotenv

# Load the values from the .env file (JWT_SECRET_KEY and friends).
load_dotenv()

# ---------------------------------------------------------------------------
# Configuration (read once from the environment).
# ---------------------------------------------------------------------------

# The secret used to sign every token. If it is missing we stop early with a
# clear message, because a signing key is not optional.
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
if not JWT_SECRET_KEY:
    raise RuntimeError(
        "JWT_SECRET_KEY is not set. Copy .env.example to .env and set it."
    )

# The signing algorithm. HS256 is a simple, widely used default.
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")

# How long tokens live. We read them as text from .env and turn them into numbers.
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------

def hash_password(plain_password: str) -> str:
    """Turn a plain-text password into a safe, salted BCRYPT hash."""
    # bcrypt works on bytes, so we encode the text first.
    password_bytes = plain_password.encode("utf-8")
    # gensalt() adds random "salt" so two identical passwords hash differently.
    hashed = bcrypt.hashpw(password_bytes, bcrypt.gensalt())
    # Store the hash as text in the database.
    return hashed.decode("utf-8")


def verify_password(plain_password: str, password_hash: str) -> bool:
    """Return True if the plain password matches the stored hash."""
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            password_hash.encode("utf-8"),
        )
    except ValueError:
        # A malformed hash in the database should fail closed, not crash.
        return False


# ---------------------------------------------------------------------------
# JSON Web Tokens (JWT)
# ---------------------------------------------------------------------------

def _create_token(subject: str, token_type: str, expires_delta: timedelta) -> str:
    """
    Build and sign a JWT.

    - subject: who the token is about (we use the user's id).
    - token_type: "access" or "refresh" so we can tell them apart.
    - expires_delta: how long from now the token stays valid.
    """
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(subject),        # "subject" — the user id
        "type": token_type,         # our own marker: access vs refresh
        "iat": now,                 # "issued at" — when it was created
        "exp": now + expires_delta,  # "expires" — when it stops working
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def create_access_token(subject: str) -> str:
    """A short-lived token the browser sends with every protected request."""
    return _create_token(
        subject,
        "access",
        timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )


def create_refresh_token(subject: str) -> str:
    """A longer-lived token used only to get a fresh access token."""
    return _create_token(
        subject,
        "refresh",
        timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
    )


def decode_token(token: str) -> dict:
    """
    Read a token back into its payload dictionary.

    Raises jwt.PyJWTError (or a subclass like ExpiredSignatureError) if the
    token is invalid, tampered with, or expired. Callers should catch that.
    """
    return jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
