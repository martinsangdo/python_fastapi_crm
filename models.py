"""
models.py
---------
The database tables, described as Python classes ("models").

We have four models:
  * `User`        — a person who can log in (the authentication module).
  * `Role`        — a named group a user belongs to, e.g. Admin / Manager / Sales.
  * `Permission`  — one thing that can be done, e.g. "customers.read".
  * `role_permissions` — the link table saying which permissions a role has.

Together the last three make up "RBAC" (Role-Based Access Control). To answer
"can this user do X?" you follow: user -> role -> permissions.

Each class attribute becomes a column. SQLAlchemy turns these classes into
real SQL tables for us (see `Base.metadata.create_all(...)` in app.py). These
models mirror the tables in `sql/rbac.sql`.
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, Table, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from database import Base


# ---------------------------------------------------------------------------
# role_permissions — the many-to-many link between roles and permissions
# ---------------------------------------------------------------------------
# This is a plain link table (no extra columns of its own), so we describe it
# with SQLAlchemy's `Table` helper rather than a full class. One row means
# "this role has this permission".
#
# The pair (role_id, permission_id) is the primary key, so the same permission
# cannot be attached to the same role twice. ON DELETE CASCADE means deleting a
# role or a permission automatically removes its link rows.
role_permissions = Table(
    "role_permissions",
    Base.metadata,
    Column(
        "role_id",
        UUID(as_uuid=True),
        ForeignKey("roles.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "permission_id",
        UUID(as_uuid=True),
        ForeignKey("permissions.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class User(Base):
    """One row = one person who can log in to the CRM."""

    # The name of the real table created in the database.
    __tablename__ = "users"

    # A unique ID for every user. We use a UUID (a long random identifier)
    # instead of a plain number so IDs are not guessable.
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # The user's email. It must be unique (no two users share one) and we
    # add index=True so looking a user up by email stays fast.
    email = Column(String(255), unique=True, index=True, nullable=False)

    # The BCRYPT hash of the password. We NEVER store the real password.
    password_hash = Column(String(255), nullable=False)

    # The person's display name, shown in the UI after they log in.
    full_name = Column(String(255), nullable=False)

    # A simple on/off switch. Set to False to disable an account without
    # deleting it (a disabled user cannot log in).
    is_active = Column(Boolean, default=True, nullable=False)

    # When the account was created. The database fills this in automatically.
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # When the account was last changed. Updated automatically on every save.
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # The last time the user successfully logged in. Empty until their
    # first login, so this column is allowed to be NULL.
    last_login = Column(DateTime(timezone=True), nullable=True)

    # The role this user belongs to (Admin, Manager, Sales, ...). NULL is
    # allowed so a user can exist before a role is assigned. If the role is
    # deleted, this is set back to NULL (see ondelete="SET NULL") rather than
    # deleting the user.
    role_id = Column(
        UUID(as_uuid=True),
        ForeignKey("roles.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )

    # Convenience link to the full Role object. Lets you write `user.role`
    # instead of looking the role up by id yourself.
    role = relationship("Role", back_populates="users")

    def __repr__(self) -> str:
        # A friendly text version, handy when debugging in the console.
        return f"<User email={self.email!r} active={self.is_active}>"


class Role(Base):
    """One row = one named group of users (e.g. Admin, Manager, Sales)."""

    __tablename__ = "roles"

    # Random UUID primary key, generated in Python for each new row.
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Machine-friendly code used in application logic, e.g. 'ADMIN'. Unique so
    # it can be looked up reliably.
    code = Column(String(50), unique=True, nullable=False)

    # Human-friendly display name shown in the UI, e.g. 'Administrator'.
    name = Column(String(100), unique=True, nullable=False)

    # Optional longer explanation of what the role is for.
    description = Column(Text, nullable=True)

    # TRUE for roles that ship with the system (and should not be deleted by
    # users). FALSE for custom roles someone creates later.
    is_system = Column(Boolean, default=True, nullable=False)

    # When the role was created / last changed. The database fills these in.
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # All users who currently have this role.
    users = relationship("User", back_populates="role")

    # All permissions granted to this role, via the role_permissions link table.
    permissions = relationship(
        "Permission",
        secondary=role_permissions,
        back_populates="roles",
    )

    def __repr__(self) -> str:
        return f"<Role code={self.code!r}>"


class Permission(Base):
    """One row = one thing that can be done, e.g. "customers.read"."""

    __tablename__ = "permissions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # The feature area, e.g. 'customers', 'orders', 'reports'.
    module = Column(String(100), nullable=False)

    # The operation, e.g. 'read', 'create', 'update', 'delete', 'view'.
    action = Column(String(50), nullable=False)

    # The full permission string "module.action", e.g. 'customers.read'.
    # Unique so each permission exists exactly once — this is what the app checks.
    code = Column(String(150), unique=True, nullable=False)

    # Optional description of what the permission grants.
    description = Column(Text, nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Every role that has been granted this permission.
    roles = relationship(
        "Role",
        secondary=role_permissions,
        back_populates="permissions",
    )

    def __repr__(self) -> str:
        return f"<Permission code={self.code!r}>"
