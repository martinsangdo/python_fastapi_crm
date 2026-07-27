"""
routers/auth.py
---------------
The HTTP layer of authentication: every /auth/* endpoint lives here.

This file is intentionally thin. Each route:
1. Receives validated data (thanks to the Pydantic schemas).
2. Calls a function in auth_service.py to do the real work.
3. Turns the result (or a ValueError) into an HTTP response.

Endpoints:
    POST /auth/register         -> create an account
    POST /auth/login            -> get access + refresh tokens
    POST /auth/refresh          -> swap a refresh token for new tokens
    POST /auth/logout           -> client-side token disposal (see note below)
    GET  /auth/me               -> the logged-in user (protected)
    POST /auth/change-password  -> change your password (protected)
"""

import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

import auth_service
from database import get_db
from dependencies import get_current_user
from models import User
from schemas import (
    PasswordChange,
    RefreshRequest,
    TokenPair,
    UserLogin,
    UserPublic,
    UserRegister,
)
from security import create_access_token, create_refresh_token, decode_token

# All routes below are grouped under /auth and tagged "auth" in the docs.
router = APIRouter(prefix="/auth", tags=["auth"])


def _tokens_for(user: User) -> TokenPair:
    """Build a fresh access + refresh token pair for a user."""
    return TokenPair(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
    )


@router.post(
    "/register",
    response_model=UserPublic,
    status_code=status.HTTP_201_CREATED,
)
def register(data: UserRegister, db: Session = Depends(get_db)):
    """Create a new account and return the safe (password-free) user view."""
    try:
        user = auth_service.register_user(db, data)
    except ValueError as error:
        # e.g. the email is already taken.
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error))
    return user


@router.post("/login", response_model=TokenPair)
def login(data: UserLogin, db: Session = Depends(get_db)):
    """Check the email + password and hand back a token pair."""
    try:
        user = auth_service.authenticate_user(db, data)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=str(error)
        )
    return _tokens_for(user)


@router.post("/refresh", response_model=TokenPair)
def refresh(data: RefreshRequest, db: Session = Depends(get_db)):
    """
    Exchange a valid refresh token for a brand-new token pair.

    This lets a user stay logged in without re-entering their password once
    the short-lived access token expires.
    """
    invalid = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired refresh token.",
    )

    try:
        payload = decode_token(data.refresh_token)
    except jwt.PyJWTError:
        raise invalid

    # It must actually be a refresh token, not an access token.
    if payload.get("type") != "refresh":
        raise invalid

    user_id = payload.get("sub")
    user = auth_service.get_user_by_id(db, user_id) if user_id else None
    if user is None or not user.is_active:
        raise invalid

    return _tokens_for(user)


@router.post("/logout")
def logout(_: User = Depends(get_current_user)):
    """
    Log the current user out.

    Because JWTs are stateless, "logging out" means the client throws its
    tokens away (our frontend clears them from storage). We require a valid
    token here so only a real, logged-in caller gets a success response.

    A production system that needs server-side logout would add a token
    "blocklist"; that is out of scope for this scaffold.
    """
    return {"detail": "Logged out. Please discard your tokens."}


@router.get("/me", response_model=UserPublic)
def read_me(current_user: User = Depends(get_current_user)):
    """Return the profile of whoever is currently logged in."""
    return current_user


@router.post("/change-password", status_code=status.HTTP_200_OK)
def change_password(
    data: PasswordChange,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Change the logged-in user's password after checking the old one."""
    try:
        auth_service.change_password(db, current_user, data)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)
        )
    return {"detail": "Password changed successfully."}
