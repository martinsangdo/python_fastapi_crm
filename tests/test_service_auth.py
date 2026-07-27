"""
tests/test_service_auth.py
--------------------------
SERVICE-LAYER tests for auth_service.py.

These bypass HTTP entirely and call the plain business-logic functions with a
real (in-memory SQLite) session from the `db_session` fixture. They assert the
behaviours the router relies on: normalisation, uniqueness, password checks, the
last_login stamp, and the ValueError signalling used to map to HTTP statuses.
"""

import auth_service
from schemas import PasswordChange, UserLogin, UserRegister
from security import verify_password

from conftest import PASSWORD


# ---------------------------------------------------------------------------
# Lookups
# ---------------------------------------------------------------------------

def test_get_user_by_email_found_and_missing(db_session, seed):
    found = auth_service.get_user_by_email(db_session, "admin@example.com")
    assert found is not None
    assert found.email == "admin@example.com"

    assert auth_service.get_user_by_email(db_session, "nobody@example.com") is None


def test_get_user_by_id_found_and_missing(db_session, seed):
    admin = seed["users"]["admin"]
    assert auth_service.get_user_by_id(db_session, admin.id).id == admin.id
    # A syntactically valid but unused UUID returns None (not an error).
    import uuid

    assert auth_service.get_user_by_id(db_session, uuid.uuid4()) is None


# ---------------------------------------------------------------------------
# register_user
# ---------------------------------------------------------------------------

def test_register_user_creates_account(db_session, seed):
    data = UserRegister(
        email="New.User@Example.com",
        full_name="  New User  ",
        password="secret123",
    )
    user = auth_service.register_user(db_session, data)

    # Email is lowercased/stripped and the name is stripped.
    assert user.email == "new.user@example.com"
    assert user.full_name == "New User"
    # Only a hash is stored — never the plain password.
    assert user.password_hash != "secret123"
    assert verify_password("secret123", user.password_hash)
    # The database filled in id + timestamps.
    assert user.id is not None
    assert user.created_at is not None


def test_register_user_duplicate_email_raises(db_session, seed):
    data = UserRegister(
        email="admin@example.com",
        full_name="Copycat",
        password="secret123",
    )
    try:
        auth_service.register_user(db_session, data)
        assert False, "expected ValueError for duplicate email"
    except ValueError as error:
        assert "already exists" in str(error)


def test_register_user_duplicate_is_case_insensitive(db_session, seed):
    # "ADMIN@EXAMPLE.COM" normalises to the existing admin address.
    data = UserRegister(
        email="ADMIN@EXAMPLE.COM",
        full_name="Copycat",
        password="secret123",
    )
    try:
        auth_service.register_user(db_session, data)
        assert False, "expected ValueError for duplicate (case-insensitive) email"
    except ValueError:
        pass


# ---------------------------------------------------------------------------
# authenticate_user
# ---------------------------------------------------------------------------

def test_authenticate_user_success_stamps_last_login(db_session, seed):
    admin = seed["users"]["admin"]
    assert admin.last_login is None

    user = auth_service.authenticate_user(
        db_session, UserLogin(email="admin@example.com", password=PASSWORD)
    )
    assert user.id == admin.id
    # A successful login records the time.
    assert user.last_login is not None


def test_authenticate_user_wrong_password_raises(db_session, seed):
    try:
        auth_service.authenticate_user(
            db_session, UserLogin(email="admin@example.com", password="nope")
        )
        assert False, "expected ValueError for wrong password"
    except ValueError as error:
        assert "Incorrect email or password" in str(error)


def test_authenticate_user_unknown_email_raises(db_session, seed):
    try:
        auth_service.authenticate_user(
            db_session, UserLogin(email="ghost@example.com", password=PASSWORD)
        )
        assert False, "expected ValueError for unknown email"
    except ValueError as error:
        # Same message as wrong password (no user enumeration).
        assert "Incorrect email or password" in str(error)


def test_authenticate_user_disabled_account_raises(db_session, seed):
    # The disabled user has the correct password, so we reach the is_active check.
    try:
        auth_service.authenticate_user(
            db_session, UserLogin(email="disabled@example.com", password=PASSWORD)
        )
        assert False, "expected ValueError for disabled account"
    except ValueError as error:
        assert "disabled" in str(error).lower()


# ---------------------------------------------------------------------------
# change_password
# ---------------------------------------------------------------------------

def test_change_password_success(db_session, seed):
    admin = seed["users"]["admin"]
    auth_service.change_password(
        db_session,
        admin,
        PasswordChange(current_password=PASSWORD, new_password="brandnew123"),
    )
    # The stored hash now matches the new password, not the old one.
    assert verify_password("brandnew123", admin.password_hash)
    assert not verify_password(PASSWORD, admin.password_hash)


def test_change_password_wrong_current_raises(db_session, seed):
    admin = seed["users"]["admin"]
    try:
        auth_service.change_password(
            db_session,
            admin,
            PasswordChange(current_password="wrong", new_password="brandnew123"),
        )
        assert False, "expected ValueError for wrong current password"
    except ValueError as error:
        assert "incorrect" in str(error).lower()
    # The password must be unchanged after a failed attempt.
    assert verify_password(PASSWORD, admin.password_hash)
