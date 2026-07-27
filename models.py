"""
models.py
---------
The database tables, described as Python classes ("models").

Right now there is a single model: `User`. It maps to a `users` table in
PostgreSQL and stores everything we need for authentication.

Each class attribute becomes a column. SQLAlchemy turns these classes into
real SQL tables for us (see `Base.metadata.create_all(...)` in app.py).
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from database import Base


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

    def __repr__(self) -> str:
        # A friendly text version, handy when debugging in the console.
        return f"<User email={self.email!r} active={self.is_active}>"
