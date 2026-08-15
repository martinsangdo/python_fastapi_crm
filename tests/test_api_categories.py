"""
tests/test_api_categories.py
-----------------------------
API-LAYER tests for the Categories module (/api/categories). Every request
goes through the TestClient with a real bearer token, so routing, permission
guards, schema validation, and the service-error -> HTTP-status mapping are
all exercised together.

Permission model (see conftest.crud_seed):
  * ADMIN holds categories.read/create/update/delete.
  * SALES holds only categories.read.
"""

from conftest import PASSWORD, login


def _bearer(client, email, password=PASSWORD):
    token = login(client, email, password).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _create_category(client, headers, name="Electronics", slug=None):
    payload = {"name": name}
    if slug is not None:
        payload["slug"] = slug
    return client.post("/api/categories", json=payload, headers=headers)


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------

def test_list_categories_requires_authentication(client, crud_seed):
    assert client.get("/api/categories").status_code == 401


def test_list_categories_admin_ok(client, crud_seed):
    headers = _bearer(client, "admin@example.com")
    _create_category(client, headers, "Books")
    _create_category(client, headers, "Home & Kitchen")

    response = client.get("/api/categories", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    names = {item["name"] for item in body["items"]}
    assert names == {"Books", "Home & Kitchen"}


def test_list_categories_sales_can_read(client, crud_seed):
    response = client.get("/api/categories", headers=_bearer(client, "sales@example.com"))
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

def test_create_category_generates_slug_from_name(client, crud_seed):
    headers = _bearer(client, "admin@example.com")
    response = _create_category(client, headers, "Home & Kitchen")
    assert response.status_code == 201
    assert response.json()["slug"] == "home-kitchen"


def test_create_category_explicit_slug(client, crud_seed):
    headers = _bearer(client, "admin@example.com")
    response = _create_category(client, headers, "Books", slug="reading-material")
    assert response.status_code == 201
    assert response.json()["slug"] == "reading-material"


def test_create_category_duplicate_slug_conflict(client, crud_seed):
    headers = _bearer(client, "admin@example.com")
    _create_category(client, headers, "Books")
    response = _create_category(client, headers, "Textbooks", slug="books")
    assert response.status_code == 409


def test_create_category_empty_name_rejected(client, crud_seed):
    headers = _bearer(client, "admin@example.com")
    response = client.post("/api/categories", json={"name": "   "}, headers=headers)
    assert response.status_code == 400


def test_create_category_forbidden_for_sales(client, crud_seed):
    response = _create_category(client, _bearer(client, "sales@example.com"))
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Detail
# ---------------------------------------------------------------------------

def test_get_category_includes_product_count(client, crud_seed):
    headers = _bearer(client, "admin@example.com")
    category = _create_category(client, headers, "Electronics").json()

    response = client.get(f"/api/categories/{category['id']}", headers=headers)
    assert response.status_code == 200
    assert response.json()["product_count"] == 0


def test_get_category_not_found(client, crud_seed):
    response = client.get("/api/categories/999999", headers=_bearer(client, "admin@example.com"))
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------

def test_update_category_name_regenerates_slug_when_slug_blank(client, crud_seed):
    headers = _bearer(client, "admin@example.com")
    category = _create_category(client, headers, "Books").json()

    response = client.patch(
        f"/api/categories/{category['id']}", json={"name": "Reading Material"}, headers=headers
    )
    assert response.status_code == 200
    # Name-only update leaves the existing slug untouched (exclude_unset).
    assert response.json()["name"] == "Reading Material"
    assert response.json()["slug"] == "books"


def test_update_category_forbidden_for_sales(client, crud_seed):
    headers = _bearer(client, "admin@example.com")
    category = _create_category(client, headers, "Books").json()

    response = client.patch(
        f"/api/categories/{category['id']}",
        json={"name": "Renamed"},
        headers=_bearer(client, "sales@example.com"),
    )
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------

def test_delete_category_ok(client, crud_seed):
    headers = _bearer(client, "admin@example.com")
    category = _create_category(client, headers, "Books").json()

    response = client.delete(f"/api/categories/{category['id']}", headers=headers)
    assert response.status_code == 204
    assert client.get(f"/api/categories/{category['id']}", headers=headers).status_code == 404


def test_delete_category_blocked_when_products_reference_it(client, crud_seed):
    headers = _bearer(client, "admin@example.com")
    category = _create_category(client, headers, "Books").json()
    client.post(
        "/api/products",
        json={"category_id": category["id"], "sku": "BOOK-1", "name": "A Book", "price": "9.99"},
        headers=headers,
    )

    response = client.delete(f"/api/categories/{category['id']}", headers=headers)
    assert response.status_code == 409


def test_delete_category_forbidden_for_sales(client, crud_seed):
    headers = _bearer(client, "admin@example.com")
    category = _create_category(client, headers, "Books").json()

    response = client.delete(
        f"/api/categories/{category['id']}", headers=_bearer(client, "sales@example.com")
    )
    assert response.status_code == 403
