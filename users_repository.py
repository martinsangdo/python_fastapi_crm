"""
users_repository.py
-------------------
The "data access" layer for the Users module.

Every function here does ONE thing: talk to the database (through a SQLAlchemy
session) and hand back plain SQLAlchemy objects. There is no business logic and
no HTTP knowledge — that keeps these functions tiny and easy to reuse.

The service layer (users_service.py) calls into this file; the router calls the
service. Keeping the layers separate is what makes the code easy to follow.
"""

from typing import Optional, Tuple

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from models import Role, User

# The columns a client is allowed to sort by. We map the public sort name to the
# real model column. Anything not in this dict falls back to "created_at", so a
# bad/unknown sort value can never crash the query or leak internals.
_SORTABLE_COLUMNS = {
    "created_at": User.created_at,
    "email": User.email,
    "full_name": User.full_name,
    "last_login": User.last_login,
}


def list_users(
    db: Session,
    *,
    search: Optional[str] = None,
    role_id=None,
    is_active: Optional[bool] = None,
    sort: str = "created_at",
    order: str = "desc",
    page: int = 1,
    page_size: int = 20,
) -> Tuple[list[User], int]:
    """
    Return one page of users plus the TOTAL number that matched the filters.

    Filtering:
      - search:    matches email OR full name (case-insensitive, partial).
      - role_id:   only users with that role.
      - is_active: True (active only) / False (inactive only) / None (all).

    The total is counted BEFORE paging so the UI can show "page 2 of 7".
    """
    query = db.query(User)

    # ---- filters ----------------------------------------------------------
    if search:
        like = f"%{search.strip()}%"
        query = query.filter(
            or_(User.email.ilike(like), User.full_name.ilike(like))
        )

    if role_id is not None:
        query = query.filter(User.role_id == role_id)

    if is_active is not None:
        query = query.filter(User.is_active.is_(is_active))

    # Count the matches before we slice the query into a single page.
    total = query.count()

    # ---- sorting ----------------------------------------------------------
    column = _SORTABLE_COLUMNS.get(sort, User.created_at)
    query = query.order_by(column.asc() if order == "asc" else column.desc())

    # ---- paging -----------------------------------------------------------
    # Clamp to sensible bounds so a client cannot ask for page 0 or 10,000 rows.
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)
    rows = query.offset((page - 1) * page_size).limit(page_size).all()

    return rows, total


def get_user(db: Session, user_id) -> Optional[User]:
    """Load one user by id (or None if there is no such user)."""
    return db.query(User).filter(User.id == user_id).first()


def get_user_by_email(db: Session, email: str) -> Optional[User]:
    """Load one user by (already-normalised) email, or None."""
    return db.query(User).filter(User.email == email).first()


def get_role(db: Session, role_id) -> Optional[Role]:
    """Load one role by id (or None)."""
    return db.query(Role).filter(Role.id == role_id).first()


def list_roles(db: Session) -> list[Role]:
    """All roles, ordered by name — used to fill the role dropdown."""
    return db.query(Role).order_by(Role.name.asc()).all()


def count_active_admins(db: Session) -> int:
    """
    How many ACTIVE users currently have the ADMIN role.

    This backs the "last admin" safety rule: the system must never be left with
    zero active administrators.
    """
    return (
        db.query(func.count(User.id))
        .join(Role, User.role_id == Role.id)
        .filter(Role.code == "ADMIN", User.is_active.is_(True))
        .scalar()
    )


def add_user(db: Session, user: User) -> User:
    """Persist a brand-new user and reload it (so id/timestamps are filled in)."""
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def save(db: Session, user: User) -> User:
    """Write pending changes on an existing user back to the database."""
    db.commit()
    db.refresh(user)
    return user


def delete_user(db: Session, user: User) -> None:
    """Permanently remove a user row (a hard delete)."""
    db.delete(user)
    db.commit()
