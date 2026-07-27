"""
auth_service.py
---------------
The authentication "business logic" lives here, in plain functions.

These functions talk to the database (through a SQLAlchemy session) and use
the helpers in security.py. They do NOT know anything about HTTP — that keeps
them easy to read and to test. The router (routers/auth.py) is the layer that
turns their results into HTTP responses.

Each function raises a ValueError with a clear message when something is wrong
(e.g. "email already registered"); the router decides which HTTP status that
maps to.
"""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from models import User
from schemas import PasswordChange, UserLogin, UserRegister
from security import hash_password, verify_password


def get_user_by_email(db: Session, email: str) -> User | None:
    """Look a user up by their email address (or None if not found)."""
    return db.query(User).filter(User.email == email).first()


def get_user_by_id(db: Session, user_id: str) -> User | None:
    """Look a user up by their id (or None if not found)."""
    return db.query(User).filter(User.id == user_id).first()


def register_user(db: Session, data: UserRegister) -> User:
    """
    Create a new user account.

    Raises ValueError if the email is already taken.
    """
    # Normalise the email so "A@X.com" and "a@x.com" are treated as the same.
    email = data.email.lower().strip()

    if get_user_by_email(db, email):
        raise ValueError("An account with this email already exists.")

    user = User(
        email=email,
        full_name=data.full_name.strip(),
        # Only the hash is stored — never the real password.
        password_hash=hash_password(data.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)  # reload so id/created_at are filled in from the database
    return user


def authenticate_user(db: Session, data: UserLogin) -> User:
    """
    Check an email + password login attempt.

    Returns the User on success. Raises ValueError on any failure. We use the
    same message for "no such user" and "wrong password" on purpose, so an
    attacker cannot tell which emails are registered.
    """
    email = data.email.lower().strip()
    user = get_user_by_email(db, email)

    # Verify the password even when the user is missing would be ideal to avoid
    # timing hints; for a beginner scaffold we keep it simple and clear.
    if user is None or not verify_password(data.password, user.password_hash):
        raise ValueError("Incorrect email or password.")

    if not user.is_active:
        raise ValueError("This account is disabled.")

    # Record the successful login time.
    user.last_login = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user)
    return user


def change_password(db: Session, user: User, data: PasswordChange) -> None:
    """
    Change the password of an already-logged-in user.

    Raises ValueError if the current password is wrong.
    """
    if not verify_password(data.current_password, user.password_hash):
        raise ValueError("Your current password is incorrect.")

    user.password_hash = hash_password(data.new_password)
    db.commit()
