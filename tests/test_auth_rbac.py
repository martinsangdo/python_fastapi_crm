"""
tests/test_auth_rbac.py
-----------------------
Tests for the RBAC integration of the authentication module:

  * Successful login
  * Invalid password
  * Disabled user
  * Login returns role
  * Login returns permissions (loaded from the database)
  * Login navigation is filtered by permissions
  * GET /auth/me returns profile + role + permissions + navigation
  * JWT contents / validation (identity claims only, NEVER permissions)
  * The require_permission authorization dependency (allow + deny)
"""

import pytest
from fastapi import HTTPException

from conftest import PASSWORD, login


# ---------------------------------------------------------------------------
# Login — happy path
# ---------------------------------------------------------------------------

def test_login_success_returns_tokens(client, seed):
    response = login(client, "admin@example.com")
    assert response.status_code == 200
    body = response.json()
    # Backward-compatible token fields are still present.
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["token_type"] == "bearer"
    # The user profile is present and never leaks the password hash.
    assert body["user"]["email"] == "admin@example.com"
    assert "password_hash" not in body["user"]


def test_login_invalid_password(client, seed):
    response = login(client, "admin@example.com", password="wrong-password")
    assert response.status_code == 401


def test_login_disabled_user(client, seed):
    response = login(client, "disabled@example.com")
    assert response.status_code == 401


def test_login_unknown_email(client, seed):
    response = login(client, "nobody@example.com")
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Login — role & permissions come from the database
# ---------------------------------------------------------------------------

def test_login_returns_role(client, seed):
    body = login(client, "admin@example.com").json()
    assert body["role"] is not None
    assert body["role"]["code"] == "ADMIN"
    assert body["role"]["name"] == "Administrator"


def test_login_returns_permissions(client, seed):
    body = login(client, "sales@example.com").json()
    # SALES was granted exactly these two permissions in the database.
    assert body["permissions"] == ["customers.read", "dashboard.view"]


def test_login_user_without_role_has_no_permissions(client, seed):
    body = login(client, "norole@example.com").json()
    assert body["role"] is None
    assert body["permissions"] == []
    assert body["navigation"] == []


# ---------------------------------------------------------------------------
# Navigation is derived from permissions
# ---------------------------------------------------------------------------

def test_navigation_is_filtered_by_permissions(client, seed):
    body = login(client, "sales@example.com").json()
    modules = [item["module"] for item in body["navigation"]]
    # SALES can see dashboard + customers, but NOT users (no users.read).
    assert modules == ["dashboard", "customers"]
    assert "users" not in modules
    # Each item carries the shape the frontend needs.
    first = body["navigation"][0]
    assert set(first) == {
        "module",
        "menu_title",
        "route",
        "icon",
        "required_permission",
    }


def test_navigation_admin_includes_users(client, seed):
    body = login(client, "admin@example.com").json()
    modules = [item["module"] for item in body["navigation"]]
    assert "users" in modules
    assert "dashboard" in modules


# ---------------------------------------------------------------------------
# GET /auth/me
# ---------------------------------------------------------------------------

def test_me_returns_profile_role_permissions(client, seed):
    tokens = login(client, "sales@example.com").json()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    response = client.get("/auth/me", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["user"]["email"] == "sales@example.com"
    assert body["role"]["code"] == "SALES"
    assert body["permissions"] == ["customers.read", "dashboard.view"]
    assert [i["module"] for i in body["navigation"]] == ["dashboard", "customers"]


def test_me_requires_authentication(client, seed):
    assert client.get("/auth/me").status_code == 401


def test_me_rejects_garbage_token(client, seed):
    headers = {"Authorization": "Bearer not-a-real-token"}
    assert client.get("/auth/me", headers=headers).status_code == 401


# ---------------------------------------------------------------------------
# JWT contents & validation
# ---------------------------------------------------------------------------

def test_access_token_has_identity_claims_but_no_permissions(client, seed):
    from security import decode_token

    body = login(client, "sales@example.com").json()
    payload = decode_token(body["access_token"])
    assert payload["type"] == "access"
    assert payload["sub"]                    # user_id
    assert payload["email"] == "sales@example.com"
    assert payload["role_id"]                # the SALES role id
    assert "exp" in payload                  # expiration
    # Permissions must NEVER be embedded in the token.
    assert "permissions" not in payload


def test_refresh_token_cannot_access_protected_route(client, seed):
    body = login(client, "admin@example.com").json()
    headers = {"Authorization": f"Bearer {body['refresh_token']}"}
    # A refresh token is the wrong type for get_current_user -> 401.
    assert client.get("/auth/me", headers=headers).status_code == 401


# ---------------------------------------------------------------------------
# Authorization dependency: require_permission (unit + through HTTP)
# ---------------------------------------------------------------------------

def test_require_permission_allows_and_denies(db_session, seed):
    from authorization import require_permission

    checker = require_permission("users.read")
    admin = seed["users"]["admin"]
    sales = seed["users"]["sales"]

    # ADMIN has users.read -> the dependency returns the user unchanged.
    assert checker(user=admin, db=db_session) is admin

    # SALES lacks users.read -> the dependency raises 403.
    with pytest.raises(HTTPException) as exc:
        checker(user=sales, db=db_session)
    assert exc.value.status_code == 403


def test_get_user_permission_codes_empty_for_no_role(db_session, seed):
    from authorization import get_user_permission_codes

    norole = seed["users"]["norole"]
    assert get_user_permission_codes(db_session, norole) == set()


def test_protected_users_endpoint_enforces_permission(client, seed):
    # SALES token -> GET /api/users requires users.read -> 403.
    sales_token = login(client, "sales@example.com").json()["access_token"]
    denied = client.get(
        "/api/users", headers={"Authorization": f"Bearer {sales_token}"}
    )
    assert denied.status_code == 403

    # ADMIN token -> allowed -> 200.
    admin_token = login(client, "admin@example.com").json()["access_token"]
    allowed = client.get(
        "/api/users", headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert allowed.status_code == 200
