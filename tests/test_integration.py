"""
tests/test_integration.py
-------------------------
INTEGRATION tests: end-to-end user journeys that cross several endpoints and
layers (router -> service -> repository -> database) in a single flow. Where the
other test files check one endpoint in isolation, these check that the pieces fit
together the way a real client would drive them.
"""

from conftest import PASSWORD, login


def _bearer(client, email, password=PASSWORD):
    token = login(client, email, password).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Self-service account lifecycle
# ---------------------------------------------------------------------------

def test_register_login_me_change_password_refresh_flow(client, seed):
    # 1. Register a brand-new account.
    register = client.post(
        "/auth/register",
        json={
            "email": "journey@example.com",
            "full_name": "Journey User",
            "password": "firstpass1",
        },
    )
    assert register.status_code == 201

    # 2. Log in with it.
    login_body = login(client, "journey@example.com", "firstpass1").json()
    access = login_body["access_token"]
    refresh = login_body["refresh_token"]
    # A freshly registered user has no role and therefore no permissions/menu.
    assert login_body["role"] is None
    assert login_body["permissions"] == []
    assert login_body["navigation"] == []

    # 3. GET /auth/me reflects the same identity.
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {access}"})
    assert me.status_code == 200
    assert me.json()["user"]["email"] == "journey@example.com"

    # 4. Change the password while logged in.
    changed = client.post(
        "/auth/change-password",
        headers={"Authorization": f"Bearer {access}"},
        json={"current_password": "firstpass1", "new_password": "secondpass2"},
    )
    assert changed.status_code == 200

    # 5. The old password now fails; the new one works.
    assert login(client, "journey@example.com", "firstpass1").status_code == 401
    assert login(client, "journey@example.com", "secondpass2").status_code == 200

    # 6. The refresh token still yields a working access token.
    refreshed = client.post("/auth/refresh", json={"refresh_token": refresh})
    assert refreshed.status_code == 200
    new_access = refreshed.json()["access_token"]
    assert (
        client.get(
            "/auth/me", headers={"Authorization": f"Bearer {new_access}"}
        ).status_code
        == 200
    )


# ---------------------------------------------------------------------------
# Admin-managed account lifecycle
# ---------------------------------------------------------------------------

def test_admin_creates_user_who_can_then_log_in(client, seed):
    admin = _bearer(client, "admin@example.com")
    sales_role_id = str(seed["roles"]["sales"].id)

    # Admin creates a SALES user.
    created = client.post(
        "/api/users",
        headers=admin,
        json={
            "email": "newhire@example.com",
            "full_name": "New Hire",
            "password": "welcome123",
            "role_id": sales_role_id,
        },
    )
    assert created.status_code == 201

    # The new hire can log in and inherits the SALES permissions.
    body = login(client, "newhire@example.com", "welcome123").json()
    assert body["role"]["code"] == "SALES"
    assert body["permissions"] == ["customers.read", "dashboard.view"]
    assert [i["module"] for i in body["navigation"]] == ["dashboard", "customers"]


def test_admin_deactivate_blocks_login_then_reactivate_restores(client, seed):
    admin = _bearer(client, "admin@example.com")

    # Create a user, confirm they can log in.
    created = client.post(
        "/api/users",
        headers=admin,
        json={
            "email": "toggle@example.com",
            "full_name": "Toggle User",
            "password": "secret123",
        },
    ).json()
    assert login(client, "toggle@example.com", "secret123").status_code == 200

    # Admin deactivates them -> login is refused.
    off = client.post(f"/api/users/{created['id']}/deactivate", headers=admin)
    assert off.status_code == 200
    assert login(client, "toggle@example.com", "secret123").status_code == 401

    # Admin reactivates them -> login works again.
    on = client.post(f"/api/users/{created['id']}/activate", headers=admin)
    assert on.status_code == 200
    assert login(client, "toggle@example.com", "secret123").status_code == 200


def test_admin_reset_password_lets_user_log_in_again(client, seed):
    admin = _bearer(client, "admin@example.com")
    created = client.post(
        "/api/users",
        headers=admin,
        json={
            "email": "forgot@example.com",
            "full_name": "Forgot Password",
            "password": "original123",
        },
    ).json()

    # Admin resets the password to a new value.
    reset = client.post(
        f"/api/users/{created['id']}/reset-password",
        headers=admin,
        json={"new_password": "reset456"},
    )
    assert reset.status_code == 200

    # Only the reset password works now.
    assert login(client, "forgot@example.com", "original123").status_code == 401
    assert login(client, "forgot@example.com", "reset456").status_code == 200


def test_permission_change_is_reflected_on_next_request(client, seed):
    """A live role change flows through to /api/me/permissions immediately."""
    admin = _bearer(client, "admin@example.com")
    admin_role_id = str(seed["roles"]["admin"].id)

    # Create a user with no role: no permissions.
    created = client.post(
        "/api/users",
        headers=admin,
        json={
            "email": "promote@example.com",
            "full_name": "To Be Promoted",
            "password": "secret123",
        },
    ).json()

    user_headers = _bearer(client, "promote@example.com", "secret123")
    before = client.get("/api/me/permissions", headers=user_headers)
    assert before.json()["permissions"] == []

    # Admin promotes them to ADMIN.
    promoted = client.patch(
        f"/api/users/{created['id']}",
        headers=admin,
        json={"role_id": admin_role_id},
    )
    assert promoted.status_code == 200

    # The SAME access token now sees the ADMIN permissions (loaded fresh from DB).
    after = client.get("/api/me/permissions", headers=user_headers)
    assert "users.read" in after.json()["permissions"]
