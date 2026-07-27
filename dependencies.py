"""
dependencies.py
---------------
Reusable FastAPI "dependencies" for authentication.

The star of the file is `get_current_user`. Add it to any route and FastAPI
will:
1. Read the "Authorization: Bearer <token>" header.
2. Decode and validate the JWT.
3. Load the matching user from the database.
4. Hand your route the User object — or reject the request with 401.

That means a protected route is as simple as:

    @router.get("/me")
    def me(user: User = Depends(get_current_user)):
        ...
"""

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from auth_service import get_user_by_id
from database import get_db
from models import User
from security import decode_token

# OAuth2PasswordBearer teaches FastAPI (and the /docs page) where tokens come
# from. tokenUrl points at our login route so the "Authorize" button works.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Turn a bearer token into the logged-in User, or raise 401."""

    # A single, reusable error. We keep the detail vague on purpose.
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # Step 1: decode the token. Any problem (expired, tampered, garbage)
    # raises a PyJWTError, which we turn into a clean 401.
    try:
        payload = decode_token(token)
    except jwt.PyJWTError:
        raise credentials_error

    # Step 2: make sure this is an ACCESS token, not a refresh token.
    if payload.get("type") != "access":
        raise credentials_error

    # Step 3: the "sub" claim holds the user id we stored when signing.
    user_id = payload.get("sub")
    if user_id is None:
        raise credentials_error

    # Step 4: load the user from the database.
    user = get_user_by_id(db, user_id)
    if user is None:
        raise credentials_error

    # Step 5: a disabled account is treated as not-logged-in.
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account is disabled.",
        )

    return user
