"""
tests/conftest.py
-----------------
Shared pytest fixtures for the authentication + RBAC test suite.

The app normally talks to PostgreSQL. For fast, isolated tests we swap that for
an in-memory SQLite database and override FastAPI's `get_db` dependency so every
request in a test uses the same throwaway session. We also set safe test values
for the environment variables the app reads at import time (JWT secret, etc.)
BEFORE importing any application module.
"""

import os

# --- Environment must be set BEFORE importing app modules -------------------
# security.py and database.py read these at import time (and raise if missing).
# We force our own values so tests never touch the real .env / PostgreSQL.
os.environ["JWT_SECRET_KEY"] = "test-secret-key-do-not-use-in-production"
os.environ["JWT_ALGORITHM"] = "HS256"
os.environ["ACCESS_TOKEN_EXPIRE_MINUTES"] = "30"
os.environ["REFRESH_TOKEN_EXPIRE_DAYS"] = "7"
os.environ["DATABASE_URL"] = "sqlite://"  # in-memory; real engine stays unused

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

import models  # noqa: E402,F401  (registers the models on Base)
from database import Base, get_db  # noqa: E402

# A single shared in-memory SQLite database for the whole test session. StaticPool
# keeps ONE connection so the in-memory schema/data survive across sessions.
_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False)


@pytest.fixture()
def db_session():
    """A fresh database (schema created, dropped afterwards) + a session."""
    Base.metadata.create_all(bind=_engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=_engine)


@pytest.fixture(autouse=True)
def _sqlite_uuid_lookup_shim(monkeypatch):
    """
    SQLite-only test shim.

    In production (PostgreSQL + psycopg), a user is looked up with the token's
    `sub` claim, which is a *string* UUID, and the driver compares it against the
    UUID column fine. SQLAlchemy's generic `Uuid` type — used when we run against
    SQLite in tests — instead requires a real `uuid.UUID` object at bind time. We
    coerce str -> UUID at the lookup boundary so the tests exercise the real
    get_current_user / refresh logic without changing any application code.

    Two call sites take a string `sub` and must both be shimmed:
      * dependencies.get_user_by_id  — used by get_current_user (protected routes)
      * auth_service.get_user_by_id  — used by the /auth/refresh route
    """
    import uuid as _uuid

    import auth_service
    import dependencies

    def _coercing(original):
        def _patched(db, user_id):
            if isinstance(user_id, str):
                try:
                    user_id = _uuid.UUID(user_id)
                except ValueError:
                    return None
            return original(db, user_id)

        return _patched

    monkeypatch.setattr(
        dependencies, "get_user_by_id", _coercing(dependencies.get_user_by_id)
    )
    monkeypatch.setattr(
        auth_service, "get_user_by_id", _coercing(auth_service.get_user_by_id)
    )


@pytest.fixture()
def client(db_session):
    """A TestClient whose get_db dependency yields the test session."""
    from app import app

    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Seed data — roles, permissions and users used across the tests.
# ---------------------------------------------------------------------------

# A plain password reused for every seeded user (meets the 8-char minimum).
PASSWORD = "password123"


@pytest.fixture()
def seed(db_session):
    """
    Insert a realistic RBAC data set and return a lookup dict.

    Roles:
      * ADMIN  — granted every permission (including users.read).
      * SALES  — granted only dashboard.view + customers.read.
    Users:
      * admin@example.com    -> ADMIN, active
      * sales@example.com    -> SALES, active
      * norole@example.com   -> no role, active
      * disabled@example.com -> SALES, INACTIVE
    """
    from models import Permission, Role, User
    from security import hash_password

    codes = [
        "dashboard.view",
        "customers.read",
        "reports.view",
        "users.read",
        "users.create",
        "users.update",
        "users.delete",
    ]
    permissions = {}
    for code in codes:
        module, action = code.split(".")
        perm = Permission(module=module, action=action, code=code)
        db_session.add(perm)
        permissions[code] = perm

    admin_role = Role(code="ADMIN", name="Administrator", is_system=True)
    admin_role.permissions = list(permissions.values())

    sales_role = Role(code="SALES", name="Sales", is_system=False)
    sales_role.permissions = [permissions["dashboard.view"], permissions["customers.read"]]

    db_session.add_all([admin_role, sales_role])

    admin = User(
        email="admin@example.com",
        full_name="Admin User",
        password_hash=hash_password(PASSWORD),
        is_active=True,
        role=admin_role,
    )
    sales = User(
        email="sales@example.com",
        full_name="Sales User",
        password_hash=hash_password(PASSWORD),
        is_active=True,
        role=sales_role,
    )
    norole = User(
        email="norole@example.com",
        full_name="No Role User",
        password_hash=hash_password(PASSWORD),
        is_active=True,
        role=None,
    )
    disabled = User(
        email="disabled@example.com",
        full_name="Disabled User",
        password_hash=hash_password(PASSWORD),
        is_active=False,
        role=sales_role,
    )
    db_session.add_all([admin, sales, norole, disabled])
    db_session.commit()

    return {
        "password": PASSWORD,
        "permissions": permissions,
        "roles": {"admin": admin_role, "sales": sales_role},
        "users": {
            "admin": admin,
            "sales": sales,
            "norole": norole,
            "disabled": disabled,
        },
    }


def login(client, email, password=PASSWORD):
    """Helper: POST /auth/login and return the (response, json) pair."""
    response = client.post("/auth/login", json={"email": email, "password": password})
    return response
