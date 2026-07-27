"""
users_schemas.py
----------------
Pydantic "schemas" for the Users administration module.

These describe the SHAPE of the data going in and out of the /api/users API,
separately from the SQLAlchemy models in models.py. Request schemas validate
what an admin sends us; response schemas make sure we only ever send back safe
fields (never the password hash).

The plain authentication schemas live in schemas.py; the admin-only ones live
here so the two concerns stay easy to tell apart.
"""

import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# ---------------------------------------------------------------------------
# Small shared pieces
# ---------------------------------------------------------------------------

class RoleSummary(BaseModel):
    """A tiny view of a role — enough to show it in a list or a dropdown."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name: str


# ---------------------------------------------------------------------------
# Requests (data coming IN from an admin)
# ---------------------------------------------------------------------------

class UserAdminCreate(BaseModel):
    """Body for POST /api/users — an admin creating an account for someone."""

    email: EmailStr
    full_name: str = Field(min_length=1, max_length=255)
    # Same 8-character minimum as self-service registration (see schemas.py).
    password: str = Field(min_length=8, max_length=128)
    # A user may be created without a role and assigned one later.
    role_id: Optional[uuid.UUID] = None
    is_active: bool = True


class UserAdminUpdate(BaseModel):
    """
    Body for PATCH /api/users/{id} — a partial update.

    Every field is optional: only the fields actually sent are changed. Sending
    `role_id: null` clears the role; leaving `role_id` out keeps it as-is. The
    service layer relies on Pydantic's "which fields were set" tracking to tell
    those two cases apart. Email is intentionally NOT editable here.
    """

    full_name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    role_id: Optional[uuid.UUID] = None
    is_active: Optional[bool] = None


class UserAdminPasswordReset(BaseModel):
    """Body for POST /api/users/{id}/reset-password."""

    new_password: str = Field(min_length=8, max_length=128)


# ---------------------------------------------------------------------------
# Responses (data going OUT to the browser) — never include password_hash
# ---------------------------------------------------------------------------

class UserListItem(BaseModel):
    """One row in the users list table."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    full_name: str
    is_active: bool
    role: Optional[RoleSummary] = None
    last_login: Optional[datetime] = None
    created_at: datetime


class UserListPage(BaseModel):
    """A single page of users, plus the numbers the UI needs for paging."""

    items: List[UserListItem]
    total: int          # total matching users across all pages
    page: int           # the current page number (1-based)
    page_size: int      # how many rows per page
    total_pages: int    # total number of pages


class UserAdminDetail(BaseModel):
    """The full, safe view of one user (used by detail + after create/update)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    full_name: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
    last_login: Optional[datetime] = None
    role: Optional[RoleSummary] = None
    # The effective permission codes granted by the user's role (read-only).
    permissions: List[str] = []


class CurrentPermissions(BaseModel):
    """Body of GET /api/me/permissions — used by the UI to show/hide controls."""

    permissions: List[str]
