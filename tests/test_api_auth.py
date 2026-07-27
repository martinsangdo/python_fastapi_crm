"""
tests/test_api_auth.py
----------------------
API-LAYER tests for the /auth/* endpoints, the HTML pages, and the sample
protected endpoint (/api/protected). Everything here goes through FastAPI's
TestClient, so it exercises routing, request/response schemas, status codes and
the authentication dependency end to end.

(RBAC-specific login/me behaviour is covered in test_auth_rbac.py; this file
focuses on register/refresh/logout/change-password, validation, and the shells.)
"""

from conftest import PASSWORD, login


def _bearer(client, email, password=PASSWORD):
    """Log in and return an Authorization header dict for that user."""
    token = login(client, email, password).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# POST /auth/register
# ---------------------------------------------------------------------------

def test_register_success(client, seed):
    response = client.post(
        "/auth/register",
        json={
            "email": "signup@example.com",
            "full_name": "Sign Up",
            "password": "secret123",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "signup@example.com"
    assert body["is_active"] is True
    # The response schema never leaks the password hash.
    assert "password_hash" not in body


def test_register_duplicate_email_conflict(client, seed):
    response = client.post(
        "/auth/register",
        json={
            "email": "admin@example.com",
            "full_name": "Copycat",
            "password": "secret123",
        },
    )
    assert response.status_code == 409


def test_register_invalid_email_422(client, seed):
    response = client.post(
        "/auth/register",
        json={"email": "not-an-email", "full_name": "X", "password": "secret123"},
    )
    assert response.status_code == 422


def test_register_short_password_422(client, seed):
    response = client.post(
        "/auth/register",
        json={"email": "x@example.com", "full_name": "X", "password": "short"},
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# POST /auth/refresh
# ---------------------------------------------------------------------------

def test_refresh_returns_new_token_pair(client, seed):
    refresh_token = login(client, "admin@example.com").json()["refresh_token"]
    response = client.post("/auth/refresh", json={"refresh_token": refresh_token})
    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["token_type"] == "bearer"


def test_refresh_rejects_access_token(client, seed):
    # Passing an ACCESS token where a refresh token is expected -> 401.
    access_token = login(client, "admin@example.com").json()["access_token"]
    response = client.post("/auth/refresh", json={"refresh_token": access_token})
    assert response.status_code == 401


def test_refresh_rejects_garbage(client, seed):
    response = client.post("/auth/refresh", json={"refresh_token": "not-a-token"})
    assert response.status_code == 401


def test_refresh_rejects_disabled_user(client, seed):
    # Mint a refresh token for the disabled user directly, then try to use it.
    from security import create_refresh_token

    disabled = seed["users"]["disabled"]
    token = create_refresh_token(disabled.id)
    response = client.post("/auth/refresh", json={"refresh_token": token})
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# POST /auth/logout
# ---------------------------------------------------------------------------

def test_logout_requires_authentication(client, seed):
    assert client.post("/auth/logout").status_code == 401


def test_logout_with_valid_token(client, seed):
    response = client.post("/auth/logout", headers=_bearer(client, "admin@example.com"))
    assert response.status_code == 200
    assert "discard" in response.json()["detail"].lower()


# ---------------------------------------------------------------------------
# POST /auth/change-password
# ---------------------------------------------------------------------------

def test_change_password_success_then_login_with_new(client, seed):
    headers = _bearer(client, "sales@example.com")
    response = client.post(
        "/auth/change-password",
        headers=headers,
        json={"current_password": PASSWORD, "new_password": "newpass123"},
    )
    assert response.status_code == 200

    # The old password no longer works; the new one does.
    assert login(client, "sales@example.com", PASSWORD).status_code == 401
    assert login(client, "sales@example.com", "newpass123").status_code == 200


def test_change_password_wrong_current_400(client, seed):
    headers = _bearer(client, "sales@example.com")
    response = client.post(
        "/auth/change-password",
        headers=headers,
        json={"current_password": "wrong", "new_password": "newpass123"},
    )
    assert response.status_code == 400


def test_change_password_requires_authentication(client, seed):
    response = client.post(
        "/auth/change-password",
        json={"current_password": PASSWORD, "new_password": "newpass123"},
    )
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/protected  (the sample token-guarded endpoint)
# ---------------------------------------------------------------------------

def test_protected_endpoint_with_token(client, seed):
    response = client.get(
        "/api/protected", headers=_bearer(client, "admin@example.com")
    )
    assert response.status_code == 200
    assert response.json()["email"] == "admin@example.com"


def test_protected_endpoint_without_token(client, seed):
    assert client.get("/api/protected").status_code == 401


def test_protected_endpoint_disabled_account_forbidden(client, seed):
    # Mint a valid access token for the disabled user, then call the endpoint:
    # get_current_user rejects a disabled account with 403.
    from security import create_access_token

    disabled = seed["users"]["disabled"]
    token = create_access_token(disabled.id, email=disabled.email)
    response = client.get(
        "/api/protected", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# HTML pages (Jinja2 shells) — these serve to everyone; the API enforces access.
# ---------------------------------------------------------------------------

def test_public_html_pages_render(client, seed):
    for path in ("/", "/login", "/register", "/dashboard"):
        response = client.get(path)
        assert response.status_code == 200, path
        assert "text/html" in response.headers["content-type"]


def test_admin_user_html_shells_render(client, seed):
    admin_id = seed["users"]["admin"].id
    paths = [
        "/admin/users",
        "/admin/users/new",
        f"/admin/users/{admin_id}",
        f"/admin/users/{admin_id}/edit",
    ]
    for path in paths:
        response = client.get(path)
        assert response.status_code == 200, path
        assert "text/html" in response.headers["content-type"]
