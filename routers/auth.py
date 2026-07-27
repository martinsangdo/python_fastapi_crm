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
from authorization import get_user_permission_codes
from database import get_db
from dependencies import get_current_user
from models import User
from navigation import build_navigation
from schemas import (
    LoginResponse,
    MeResponse,
    PasswordChange,
    RefreshRequest,
    RoleInfo,
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
        # The access token also carries the user's email and role_id (identity
        # only — never permissions; those come from the database each request).
        access_token=create_access_token(user.id, email=user.email, role_id=user.role_id),
        refresh_token=create_refresh_token(user.id),
    )


def _auth_context(db: Session, user: User) -> dict:
    """
    Build the RBAC part of a response: the user's role, their effective
    permission codes and the navigation menu derived from those permissions.

    The permission set is loaded from the database ONCE here and reused for both
    the `permissions` list and `navigation`, so we never query it twice
    (docs/rbac_guidelines.md §1, §4). The menu only contains items the user is
    authorized to access.
    """
    permission_codes = get_user_permission_codes(db, user)
    role = RoleInfo.model_validate(user.role) if user.role is not None else None
    return {
        "user": user,
        "role": role,
        "permissions": sorted(permission_codes),
        "navigation": build_navigation(permission_codes),
    }


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


@router.post("/login", response_model=LoginResponse)
def login(data: UserLogin, db: Session = Depends(get_db)):
    """
    Check the email + password, then hand back the tokens PLUS everything the
    frontend needs to render itself: the user profile, their role, their
    permission codes, and the permission-filtered navigation menu. The role and
    permissions are always loaded from the database (docs/rbac_guidelines.md §8).
    """
    try:
        user = auth_service.authenticate_user(db, data)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=str(error)
        )
    tokens = _tokens_for(user)
    return LoginResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        token_type=tokens.token_type,
        **_auth_context(db, user),
    )


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


@router.get("/me", response_model=MeResponse)
def read_me(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Return the profile of whoever is currently logged in, together with their
    role, permissions and navigation — all resolved fresh from the database on
    each call (docs/rbac_guidelines.md §9), so a role or permission change is
    reflected on the very next request.
    """
    return MeResponse(**_auth_context(db, current_user))


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
