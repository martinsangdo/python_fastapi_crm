"""
routers/users.py
----------------
The HTTP layer of the Users administration module: every /api/users endpoint.

Like routers/auth.py, this file stays thin. Each route:
  1. Receives validated input (thanks to the Pydantic schemas).
  2. Is guarded by `require_permission(...)` so only allowed roles get in.
  3. Calls a function in users_service.py to do the real work.
  4. Turns any typed service error into the matching HTTP status code.

Endpoints:
    GET    /api/users                       -> list (paged/filtered/sorted)
    POST   /api/users                       -> create
    GET    /api/users/{id}                  -> detail (role + permissions)
    PATCH  /api/users/{id}                  -> update name / role / active
    POST   /api/users/{id}/reset-password   -> set a new password
    POST   /api/users/{id}/activate         -> enable an account
    POST   /api/users/{id}/deactivate       -> disable an account
    DELETE /api/users/{id}                  -> hard delete
    GET    /api/roles                       -> roles (for dropdowns)
    GET    /api/me/permissions              -> the caller's own permission codes
"""

import math
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

import users_service as service
from authorization import get_user_permission_codes, require_permission
from database import get_db
from dependencies import get_current_user
from models import User
from users_repository import list_roles
from users_schemas import (
    CurrentPermissions,
    RoleSummary,
    UserAdminCreate,
    UserAdminDetail,
    UserAdminPasswordReset,
    UserAdminUpdate,
    UserListItem,
    UserListPage,
)

# No prefix: we write the full "/api/..." paths on each route so everything the
# module exposes is visible at a glance.
router = APIRouter(tags=["users"])


# ---------------------------------------------------------------------------
# Small helper: translate a service error into an HTTPException.
# ---------------------------------------------------------------------------

def _http_from_service_error(error: Exception) -> HTTPException:
    """Map our three typed service errors to the right status code."""
    if isinstance(error, service.NotFoundError):
        return HTTPException(status.HTTP_404_NOT_FOUND, detail=str(error))
    if isinstance(error, service.ConflictError):
        return HTTPException(status.HTTP_409_CONFLICT, detail=str(error))
    if isinstance(error, service.BusinessRuleError):
        return HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(error))
    # Anything unexpected bubbles up as a generic 400 rather than a 500.
    return HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(error))


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------

@router.get("/api/users", response_model=UserListPage)
def list_users(
    search: Optional[str] = None,
    role_id: Optional[uuid.UUID] = None,
    is_active: Optional[bool] = None,
    sort: str = Query("created_at"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    _: User = Depends(require_permission("users.read")),
    db: Session = Depends(get_db),
):
    """Return a filtered, sorted, paginated page of users."""
    rows, total = service.list_users(
        db,
        search=search,
        role_id=role_id,
        is_active=is_active,
        sort=sort,
        order=order,
        page=page,
        page_size=page_size,
    )
    total_pages = math.ceil(total / page_size) if total else 0
    return UserListPage(
        items=[UserListItem.model_validate(u) for u in rows],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

@router.post(
    "/api/users",
    response_model=UserAdminDetail,
    status_code=status.HTTP_201_CREATED,
)
def create_user(
    data: UserAdminCreate,
    _: User = Depends(require_permission("users.create")),
    db: Session = Depends(get_db),
):
    """Create a new account and return its full (password-free) detail view."""
    try:
        user = service.create_user_admin(db, data)
    except (service.ConflictError, service.NotFoundError) as error:
        raise _http_from_service_error(error)
    return service.to_detail(db, user)


# ---------------------------------------------------------------------------
# Detail
# ---------------------------------------------------------------------------

@router.get("/api/users/{user_id}", response_model=UserAdminDetail)
def get_user(
    user_id: uuid.UUID,
    _: User = Depends(require_permission("users.read")),
    db: Session = Depends(get_db),
):
    """Return one user, including their role and effective permission codes."""
    try:
        user = service.get_user_or_404(db, user_id)
    except service.NotFoundError as error:
        raise _http_from_service_error(error)
    return service.to_detail(db, user)


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------

@router.patch("/api/users/{user_id}", response_model=UserAdminDetail)
def update_user(
    user_id: uuid.UUID,
    data: UserAdminUpdate,
    actor: User = Depends(require_permission("users.update")),
    db: Session = Depends(get_db),
):
    """Change a user's name, role and/or active status (email is not editable)."""
    try:
        user = service.update_user_admin(db, actor, user_id, data)
    except (service.NotFoundError, service.BusinessRuleError) as error:
        raise _http_from_service_error(error)
    return service.to_detail(db, user)


# ---------------------------------------------------------------------------
# Reset password
# ---------------------------------------------------------------------------

@router.post("/api/users/{user_id}/reset-password")
def reset_password(
    user_id: uuid.UUID,
    data: UserAdminPasswordReset,
    _: User = Depends(require_permission("users.update")),
    db: Session = Depends(get_db),
):
    """Set a brand-new password for a user. The old one is never revealed."""
    try:
        service.reset_user_password(db, user_id, data.new_password)
    except service.NotFoundError as error:
        raise _http_from_service_error(error)
    return {"detail": "Password reset."}


# ---------------------------------------------------------------------------
# Activate / deactivate
# ---------------------------------------------------------------------------

@router.post("/api/users/{user_id}/activate", response_model=UserAdminDetail)
def activate_user(
    user_id: uuid.UUID,
    actor: User = Depends(require_permission("users.update")),
    db: Session = Depends(get_db),
):
    """Re-enable a disabled account."""
    try:
        user = service.activate_user(db, actor, user_id)
    except service.NotFoundError as error:
        raise _http_from_service_error(error)
    return service.to_detail(db, user)


@router.post("/api/users/{user_id}/deactivate", response_model=UserAdminDetail)
def deactivate_user(
    user_id: uuid.UUID,
    actor: User = Depends(require_permission("users.update")),
    db: Session = Depends(get_db),
):
    """Disable an account (keeps its history; blocks future logins)."""
    try:
        user = service.deactivate_user(db, actor, user_id)
    except (service.NotFoundError, service.BusinessRuleError) as error:
        raise _http_from_service_error(error)
    return service.to_detail(db, user)


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------

@router.delete("/api/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: uuid.UUID,
    actor: User = Depends(require_permission("users.delete")),
    db: Session = Depends(get_db),
):
    """Permanently delete a user (guarded against self-delete + last admin)."""
    try:
        service.delete_user(db, actor, user_id)
    except (service.NotFoundError, service.BusinessRuleError) as error:
        raise _http_from_service_error(error)
    # 204 = success, no body to return.
    return None


# ---------------------------------------------------------------------------
# Roles (for dropdowns)
# ---------------------------------------------------------------------------

@router.get("/api/roles", response_model=list[RoleSummary])
def get_roles(
    _: User = Depends(require_permission("users.read")),
    db: Session = Depends(get_db),
):
    """Return every role, so the UI can offer them in a dropdown."""
    return list_roles(db)


# ---------------------------------------------------------------------------
# The caller's own permissions (for UI show/hide) — any logged-in user
# ---------------------------------------------------------------------------

@router.get("/api/me/permissions", response_model=CurrentPermissions)
def my_permissions(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Return the permission codes the logged-in user has.

    The frontend uses this to hide buttons the user isn't allowed to use. It is
    a convenience only — the server still enforces every permission on its own.
    """
    return CurrentPermissions(
        permissions=sorted(get_user_permission_codes(db, current_user))
    )
