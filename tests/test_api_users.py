"""
tests/test_api_users.py
-----------------------
API-LAYER tests for the Users administration module (/api/users, /api/roles,
/api/me/permissions). Every request goes through the TestClient with a real
bearer token, so routing, permission guards, schema validation, and the
service-error -> HTTP-status mapping are all exercised together.

Permission model in the seed data:
  * ADMIN holds users.read/create/update/delete (plus others).
  * SALES holds only dashboard.view + customers.read, so it is forbidden from
    every /api/users write and read route.
"""

import uuid

from conftest import PASSWORD, login


def _bearer(client, email, password=PASSWORD):
    token = login(client, email, password).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# GET /api/users — list
# ---------------------------------------------------------------------------

def test_list_users_admin_ok(client, seed):
    response = client.get("/api/users", headers=_bearer(client, "admin@example.com"))
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 4
    assert body["page"] == 1
    assert body["page_size"] == 20
    assert len(body["items"]) == 4
    # List items never leak the password hash.
    assert "password_hash" not in body["items"][0]


def test_list_users_requires_authentication(client, seed):
    assert client.get("/api/users").status_code == 401


def test_list_users_forbidden_without_permission(client, seed):
    response = client.get("/api/users", headers=_bearer(client, "sales@example.com"))
    assert response.status_code == 403


def test_list_users_search_filter(client, seed):
    response = client.get(
        "/api/users",
        params={"search": "admin"},
        headers=_bearer(client, "admin@example.com"),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["email"] == "admin@example.com"


def test_list_users_active_filter_and_paging(client, seed):
    response = client.get(
        "/api/users",
        params={"is_active": "false", "page": 1, "page_size": 10},
        headers=_bearer(client, "admin@example.com"),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["email"] == "disabled@example.com"


def test_list_users_bad_order_value_422(client, seed):
    # `order` is validated against ^(asc|desc)$ by the route.
    response = client.get(
        "/api/users",
        params={"order": "sideways"},
        headers=_bearer(client, "admin@example.com"),
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# POST /api/users — create
# ---------------------------------------------------------------------------

def test_create_user_admin_ok(client, seed):
    sales_role_id = str(seed["roles"]["sales"].id)
    response = client.post(
        "/api/users",
        headers=_bearer(client, "admin@example.com"),
        json={
            "email": "created@example.com",
            "full_name": "Created User",
            "password": "secret123",
            "role_id": sales_role_id,
            "is_active": True,
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "created@example.com"
    assert body["role"]["code"] == "SALES"
    assert "password_hash" not in body


def test_create_user_duplicate_email_409(client, seed):
    response = client.post(
        "/api/users",
        headers=_bearer(client, "admin@example.com"),
        json={
            "email": "admin@example.com",
            "full_name": "Copycat",
            "password": "secret123",
        },
    )
    assert response.status_code == 409


def test_create_user_unknown_role_404(client, seed):
    response = client.post(
        "/api/users",
        headers=_bearer(client, "admin@example.com"),
        json={
            "email": "ghost@example.com",
            "full_name": "Ghost",
            "password": "secret123",
            "role_id": str(uuid.uuid4()),
        },
    )
    assert response.status_code == 404


def test_create_user_forbidden_for_sales(client, seed):
    response = client.post(
        "/api/users",
        headers=_bearer(client, "sales@example.com"),
        json={
            "email": "x@example.com",
            "full_name": "X",
            "password": "secret123",
        },
    )
    assert response.status_code == 403


def test_create_user_validation_422(client, seed):
    response = client.post(
        "/api/users",
        headers=_bearer(client, "admin@example.com"),
        json={"email": "bad", "full_name": "", "password": "short"},
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# GET /api/users/{id} — detail
# ---------------------------------------------------------------------------

def test_get_user_detail_ok(client, seed):
    sales_id = seed["users"]["sales"].id
    response = client.get(
        f"/api/users/{sales_id}", headers=_bearer(client, "admin@example.com")
    )
    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "sales@example.com"
    assert body["permissions"] == ["customers.read", "dashboard.view"]


def test_get_user_detail_not_found_404(client, seed):
    response = client.get(
        f"/api/users/{uuid.uuid4()}", headers=_bearer(client, "admin@example.com")
    )
    assert response.status_code == 404


def test_get_user_detail_forbidden_for_sales(client, seed):
    admin_id = seed["users"]["admin"].id
    response = client.get(
        f"/api/users/{admin_id}", headers=_bearer(client, "sales@example.com")
    )
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# PATCH /api/users/{id} — update
# ---------------------------------------------------------------------------

def test_update_user_name_ok(client, seed):
    sales_id = seed["users"]["sales"].id
    response = client.patch(
        f"/api/users/{sales_id}",
        headers=_bearer(client, "admin@example.com"),
        json={"full_name": "Sales Renamed"},
    )
    assert response.status_code == 200
    assert response.json()["full_name"] == "Sales Renamed"


def test_update_user_not_found_404(client, seed):
    response = client.patch(
        f"/api/users/{uuid.uuid4()}",
        headers=_bearer(client, "admin@example.com"),
        json={"full_name": "Nobody"},
    )
    assert response.status_code == 404


def test_update_move_last_admin_off_admin_role_400(client, seed):
    # The admin token is the only active admin; moving it to SALES is blocked.
    admin_id = seed["users"]["admin"].id
    sales_role_id = str(seed["roles"]["sales"].id)
    response = client.patch(
        f"/api/users/{admin_id}",
        headers=_bearer(client, "admin@example.com"),
        json={"role_id": sales_role_id},
    )
    assert response.status_code == 400


def test_update_user_forbidden_for_sales(client, seed):
    admin_id = seed["users"]["admin"].id
    response = client.patch(
        f"/api/users/{admin_id}",
        headers=_bearer(client, "sales@example.com"),
        json={"full_name": "Nope"},
    )
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# POST /api/users/{id}/reset-password
# ---------------------------------------------------------------------------

def test_reset_password_ok_then_login(client, seed):
    sales_id = seed["users"]["sales"].id
    response = client.post(
        f"/api/users/{sales_id}/reset-password",
        headers=_bearer(client, "admin@example.com"),
        json={"new_password": "adminset123"},
    )
    assert response.status_code == 200
    # The user can log in with the admin-set password.
    assert login(client, "sales@example.com", "adminset123").status_code == 200


def test_reset_password_not_found_404(client, seed):
    response = client.post(
        f"/api/users/{uuid.uuid4()}/reset-password",
        headers=_bearer(client, "admin@example.com"),
        json={"new_password": "adminset123"},
    )
    assert response.status_code == 404


def test_reset_password_forbidden_for_sales(client, seed):
    sales_id = seed["users"]["sales"].id
    response = client.post(
        f"/api/users/{sales_id}/reset-password",
        headers=_bearer(client, "sales@example.com"),
        json={"new_password": "adminset123"},
    )
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# POST /api/users/{id}/activate  &  /deactivate
# ---------------------------------------------------------------------------

def test_deactivate_then_activate(client, seed):
    headers = _bearer(client, "admin@example.com")
    sales_id = seed["users"]["sales"].id

    off = client.post(f"/api/users/{sales_id}/deactivate", headers=headers)
    assert off.status_code == 200
    assert off.json()["is_active"] is False

    on = client.post(f"/api/users/{sales_id}/activate", headers=headers)
    assert on.status_code == 200
    assert on.json()["is_active"] is True


def test_deactivate_self_400(client, seed):
    admin_id = seed["users"]["admin"].id
    response = client.post(
        f"/api/users/{admin_id}/deactivate",
        headers=_bearer(client, "admin@example.com"),
    )
    assert response.status_code == 400


def test_activate_not_found_404(client, seed):
    response = client.post(
        f"/api/users/{uuid.uuid4()}/activate",
        headers=_bearer(client, "admin@example.com"),
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /api/users/{id}
# ---------------------------------------------------------------------------

def test_delete_user_204(client, seed):
    # Create a throwaway user, then delete it.
    headers = _bearer(client, "admin@example.com")
    created = client.post(
        "/api/users",
        headers=headers,
        json={
            "email": "temp@example.com",
            "full_name": "Temp",
            "password": "secret123",
        },
    ).json()

    response = client.delete(f"/api/users/{created['id']}", headers=headers)
    assert response.status_code == 204
    # It is really gone.
    assert client.get(f"/api/users/{created['id']}", headers=headers).status_code == 404


def test_delete_self_400(client, seed):
    admin_id = seed["users"]["admin"].id
    response = client.delete(
        f"/api/users/{admin_id}", headers=_bearer(client, "admin@example.com")
    )
    assert response.status_code == 400


def test_delete_not_found_404(client, seed):
    response = client.delete(
        f"/api/users/{uuid.uuid4()}", headers=_bearer(client, "admin@example.com")
    )
    assert response.status_code == 404


def test_delete_forbidden_for_sales(client, seed):
    admin_id = seed["users"]["admin"].id
    response = client.delete(
        f"/api/users/{admin_id}", headers=_bearer(client, "sales@example.com")
    )
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# GET /api/roles
# ---------------------------------------------------------------------------

def test_get_roles_ok(client, seed):
    response = client.get("/api/roles", headers=_bearer(client, "admin@example.com"))
    assert response.status_code == 200
    codes = {r["code"] for r in response.json()}
    assert codes == {"ADMIN", "SALES"}


def test_get_roles_forbidden_for_sales(client, seed):
    response = client.get("/api/roles", headers=_bearer(client, "sales@example.com"))
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# GET /api/me/permissions — any logged-in user
# ---------------------------------------------------------------------------

def test_my_permissions_admin(client, seed):
    response = client.get(
        "/api/me/permissions", headers=_bearer(client, "admin@example.com")
    )
    assert response.status_code == 200
    perms = response.json()["permissions"]
    assert "users.read" in perms
    # The list is sorted.
    assert perms == sorted(perms)


def test_my_permissions_sales(client, seed):
    response = client.get(
        "/api/me/permissions", headers=_bearer(client, "sales@example.com")
    )
    assert response.status_code == 200
    assert response.json()["permissions"] == ["customers.read", "dashboard.view"]


def test_my_permissions_no_role_is_empty(client, seed):
    response = client.get(
        "/api/me/permissions", headers=_bearer(client, "norole@example.com")
    )
    assert response.status_code == 200
    assert response.json()["permissions"] == []


def test_my_permissions_requires_authentication(client, seed):
    assert client.get("/api/me/permissions").status_code == 401
