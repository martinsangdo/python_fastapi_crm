"""
schemas.py
----------
Pydantic "schemas" describe the SHAPE of the data going in and out of the API.

- Request schemas (what the client sends us) let FastAPI validate the input
  automatically and return clear error messages.
- Response schemas (what we send back) make sure we never leak sensitive
  fields such as the password hash.

Think of these as the public contract of the API, separate from the database
model in models.py.
"""

import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# ---------------------------------------------------------------------------
# Requests (data coming IN from the browser)
# ---------------------------------------------------------------------------

class UserRegister(BaseModel):
    """Body for POST /auth/register."""

    email: EmailStr
    full_name: str = Field(min_length=1, max_length=255)
    # Require a sensible minimum length so we do not store 1-character passwords.
    password: str = Field(min_length=8, max_length=128)


class UserLogin(BaseModel):
    """Body for POST /auth/login."""

    email: EmailStr
    password: str


class PasswordChange(BaseModel):
    """Body for POST /auth/change-password (must be logged in)."""

    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


class RefreshRequest(BaseModel):
    """Body for POST /auth/refresh."""

    refresh_token: str


# ---------------------------------------------------------------------------
# Responses (data going OUT to the browser)
# ---------------------------------------------------------------------------

class UserPublic(BaseModel):
    """A safe view of a user — note there is NO password field here."""

    # from_attributes lets us build this straight from a SQLAlchemy User object.
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    full_name: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
    last_login: Optional[datetime] = None


class TokenPair(BaseModel):
    """
    A plain pair of tokens. Still returned by POST /auth/refresh so existing
    clients keep working unchanged. Login returns the richer LoginResponse below.
    """

    access_token: str
    refresh_token: str
    # "bearer" tells the client how to send the token (Authorization: Bearer ...).
    token_type: str = "bearer"


# ---------------------------------------------------------------------------
# RBAC response pieces (role, navigation) — see docs/rbac_guidelines.md
# ---------------------------------------------------------------------------

class RoleInfo(BaseModel):
    """The logged-in user's role, as the frontend needs it. Never sensitive."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name: str


class NavigationItem(BaseModel):
    """
    One entry in the sidebar/menu. The frontend renders these dynamically; the
    backend only ever includes items the user is authorized to access.
    """

    module: str
    menu_title: str
    route: str
    icon: str
    required_permission: str


class LoginResponse(BaseModel):
    """
    Body of POST /auth/login.

    A superset of TokenPair (so it stays backward compatible), plus everything
    the frontend needs to render itself: the user profile, their role, their
    effective permission codes, and the permission-filtered navigation menu.
    None of these fields is sensitive — there is no password hash here.
    """

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserPublic
    role: Optional[RoleInfo] = None
    permissions: List[str] = []
    navigation: List[NavigationItem] = []


class MeResponse(BaseModel):
    """
    Body of GET /auth/me — the current user's profile plus their live role,
    permissions and navigation (loaded fresh from the database on every call).
    """

    user: UserPublic
    role: Optional[RoleInfo] = None
    permissions: List[str] = []
    navigation: List[NavigationItem] = []
