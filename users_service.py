"""
users_service.py
----------------
The "business logic" of the Users administration module.

These functions enforce the module's RULES (email uniqueness, the last-admin
safety net, self-protection, ...) and talk to the database through
users_repository.py. They know NOTHING about HTTP — instead they raise clear,
typed errors that the router turns into the right status code.

Three error types keep that mapping simple and readable:
  * NotFoundError      -> the router returns 404
  * ConflictError      -> the router returns 409 (e.g. duplicate email)
  * BusinessRuleError  -> the router returns 400 (e.g. "can't delete yourself")
"""

from typing import Optional

from sqlalchemy.orm import Session

import users_repository as repo
from authorization import get_user_permission_codes
from models import User
from security import hash_password
from users_schemas import (
    RoleSummary,
    UserAdminCreate,
    UserAdminDetail,
    UserAdminUpdate,
)


# ---------------------------------------------------------------------------
# Typed errors — the router maps each of these to an HTTP status code.
# ---------------------------------------------------------------------------

class NotFoundError(Exception):
    """Raised when the requested user (or role) does not exist."""


class ConflictError(Exception):
    """Raised when a value clashes with an existing one (e.g. email taken)."""


class BusinessRuleError(Exception):
    """Raised when a request is understood but breaks a module rule."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_active_admin(user: User) -> bool:
    """True if this user is currently an ACTIVE administrator."""
    return bool(user.is_active and user.role is not None and user.role.code == "ADMIN")


def _would_remove_last_admin(db: Session, user: User) -> bool:
    """
    True if removing this user's admin access (by deactivating, deleting, or
    moving them off the ADMIN role) would leave the system with NO active
    administrators.
    """
    return _is_active_admin(user) and repo.count_active_admins(db) <= 1


def to_detail(db: Session, user: User) -> UserAdminDetail:
    """
    Build the safe, full detail view of a user, including the effective
    permission codes granted by their role.
    """
    role = RoleSummary.model_validate(user.role) if user.role is not None else None
    return UserAdminDetail(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        is_active=user.is_active,
        created_at=user.created_at,
        updated_at=user.updated_at,
        last_login=user.last_login,
        role=role,
        permissions=sorted(get_user_permission_codes(db, user)),
    )


def _resolve_role(db: Session, role_id) -> None:
    """Raise NotFoundError if a (non-null) role_id does not point at a real role."""
    if role_id is not None and repo.get_role(db, role_id) is None:
        raise NotFoundError("The selected role does not exist.")


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------

def get_user_or_404(db: Session, user_id) -> User:
    """Load a user, or raise NotFoundError if there is none with that id."""
    user = repo.get_user(db, user_id)
    if user is None:
        raise NotFoundError("User not found.")
    return user


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

def create_user_admin(db: Session, data: UserAdminCreate) -> User:
    """
    Create a user on behalf of an admin.

    Raises ConflictError if the email is taken, NotFoundError if a role_id was
    given that does not exist.
    """
    email = data.email.lower().strip()

    if repo.get_user_by_email(db, email) is not None:
        raise ConflictError("An account with this email already exists.")

    _resolve_role(db, data.role_id)

    user = User(
        email=email,
        full_name=data.full_name.strip(),
        password_hash=hash_password(data.password),  # only the hash is stored
        is_active=data.is_active,
        role_id=data.role_id,
    )
    return repo.add_user(db, user)


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------

def update_user_admin(
    db: Session,
    actor: User,
    user_id,
    data: UserAdminUpdate,
) -> User:
    """
    Apply a partial update to a user.

    `actor` is the logged-in admin making the change — needed for the
    self-protection rule. Only the fields actually sent are touched.
    """
    user = get_user_or_404(db, user_id)

    # Only the fields the client actually sent. This is how we tell "clear the
    # role" (role_id present and null) apart from "leave the role alone".
    changes = data.model_dump(exclude_unset=True)

    # --- guard: deactivating ------------------------------------------------
    if changes.get("is_active") is False:
        _guard_can_deactivate(db, actor, user)

    # --- guard: changing role away from ADMIN -------------------------------
    if "role_id" in changes:
        new_role_id = changes["role_id"]
        _resolve_role(db, new_role_id)
        # Moving the final active admin onto a different (or no) role would
        # strip the system of its last administrator.
        currently_admin = _is_active_admin(user)
        new_is_admin_role = _role_is_admin(db, new_role_id)
        if currently_admin and not new_is_admin_role and _would_remove_last_admin(db, user):
            raise BusinessRuleError(
                "You cannot change the role of the last active administrator."
            )

    # --- apply --------------------------------------------------------------
    if "full_name" in changes:
        user.full_name = changes["full_name"].strip()
    if "role_id" in changes:
        user.role_id = changes["role_id"]
    if "is_active" in changes:
        user.is_active = changes["is_active"]

    return repo.save(db, user)


def _role_is_admin(db: Session, role_id) -> bool:
    """True if the given role id is the ADMIN role."""
    if role_id is None:
        return False
    role = repo.get_role(db, role_id)
    return bool(role is not None and role.code == "ADMIN")


# ---------------------------------------------------------------------------
# Activate / deactivate
# ---------------------------------------------------------------------------

def _guard_can_deactivate(db: Session, actor: User, user: User) -> None:
    """Shared checks before turning an account off."""
    if user.id == actor.id:
        raise BusinessRuleError("You cannot deactivate your own account.")
    if _would_remove_last_admin(db, user):
        raise BusinessRuleError(
            "You cannot deactivate the last active administrator."
        )


def deactivate_user(db: Session, actor: User, user_id) -> User:
    """Turn an account off (is_active = False) with the safety checks applied."""
    user = get_user_or_404(db, user_id)
    _guard_can_deactivate(db, actor, user)
    user.is_active = False
    return repo.save(db, user)


def activate_user(db: Session, actor: User, user_id) -> User:
    """Turn an account back on. Re-enabling access needs no special guard."""
    user = get_user_or_404(db, user_id)
    user.is_active = True
    return repo.save(db, user)


# ---------------------------------------------------------------------------
# Reset password
# ---------------------------------------------------------------------------

def reset_user_password(db: Session, user_id, new_password: str) -> User:
    """Set a brand-new bcrypt password hash for a user (admin-driven reset)."""
    user = get_user_or_404(db, user_id)
    user.password_hash = hash_password(new_password)
    return repo.save(db, user)


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------

def delete_user(db: Session, actor: User, user_id) -> None:
    """
    Permanently remove a user, with the same protections as deactivation:
    you cannot delete yourself, and you cannot delete the last active admin.
    """
    user = get_user_or_404(db, user_id)
    if user.id == actor.id:
        raise BusinessRuleError("You cannot delete your own account.")
    if _would_remove_last_admin(db, user):
        raise BusinessRuleError("You cannot delete the last active administrator.")
    repo.delete_user(db, user)


# ---------------------------------------------------------------------------
# Listing (thin pass-through with clamping handled in the repository)
# ---------------------------------------------------------------------------

def list_users(
    db: Session,
    *,
    search: Optional[str],
    role_id,
    is_active: Optional[bool],
    sort: str,
    order: str,
    page: int,
    page_size: int,
):
    """Return (rows, total) for a page of users. Filtering lives in the repo."""
    return repo.list_users(
        db,
        search=search,
        role_id=role_id,
        is_active=is_active,
        sort=sort,
        order=order,
        page=page,
        page_size=page_size,
    )
