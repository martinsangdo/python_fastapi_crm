"""
tests/test_api_products.py
----------------------------
API-LAYER tests for the Products module (/api/products). Every request goes
through the TestClient with a real bearer token, so routing, permission
guards, schema validation, and the service-error -> HTTP-status mapping are
all exercised together.

Permission model (see conftest.crud_seed):
  * ADMIN holds products.read/create/update/delete.
  * SALES holds only products.read.
"""

from conftest import PASSWORD, login


def _bearer(client, email, password=PASSWORD):
    token = login(client, email, password).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _create_category(client, headers, name="Electronics"):
    return client.post("/api/categories", json={"name": name}, headers=headers).json()


def _create_product(client, headers, category_id, sku="SKU-1", name="Widget", price="9.99", stock=10):
    return client.post(
        "/api/products",
        json={
            "category_id": category_id,
            "sku": sku,
            "name": name,
            "price": price,
            "stock_quantity": stock,
        },
        headers=headers,
    )


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------

def test_list_products_requires_authentication(client, crud_seed):
    assert client.get("/api/products").status_code == 401


def test_list_products_sales_can_read(client, crud_seed):
    response = client.get("/api/products", headers=_bearer(client, "sales@example.com"))
    assert response.status_code == 200


def test_list_products_filters_by_category(client, crud_seed):
    headers = _bearer(client, "admin@example.com")
    cat1 = _create_category(client, headers, "Electronics")
    cat2 = _create_category(client, headers, "Books")
    _create_product(client, headers, cat1["id"], sku="ELEC-1", name="Cable")
    _create_product(client, headers, cat2["id"], sku="BOOK-1", name="Novel")

    response = client.get(f"/api/products?category_id={cat1['id']}", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["sku"] == "ELEC-1"


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

def test_create_product_ok_and_normalizes_sku(client, crud_seed):
    headers = _bearer(client, "admin@example.com")
    category = _create_category(client, headers)
    response = _create_product(client, headers, category["id"], sku=" sku-lower ")
    assert response.status_code == 201
    body = response.json()
    assert body["sku"] == "SKU-LOWER"
    assert body["category"]["id"] == category["id"]


def test_create_product_unknown_category_404(client, crud_seed):
    headers = _bearer(client, "admin@example.com")
    response = _create_product(client, headers, category_id=999999)
    assert response.status_code == 404


def test_create_product_duplicate_sku_conflict(client, crud_seed):
    headers = _bearer(client, "admin@example.com")
    category = _create_category(client, headers)
    _create_product(client, headers, category["id"], sku="DUP-1")
    response = _create_product(client, headers, category["id"], sku="DUP-1")
    assert response.status_code == 409


def test_create_product_negative_price_rejected(client, crud_seed):
    headers = _bearer(client, "admin@example.com")
    category = _create_category(client, headers)
    response = client.post(
        "/api/products",
        json={"category_id": category["id"], "sku": "NEG-1", "name": "Bad", "price": "-1.00"},
        headers=headers,
    )
    assert response.status_code == 422


def test_create_product_forbidden_for_sales(client, crud_seed):
    headers_admin = _bearer(client, "admin@example.com")
    category = _create_category(client, headers_admin)
    response = _create_product(client, _bearer(client, "sales@example.com"), category["id"])
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Detail / activate / deactivate
# ---------------------------------------------------------------------------

def test_get_product_not_found(client, crud_seed):
    response = client.get("/api/products/999999", headers=_bearer(client, "admin@example.com"))
    assert response.status_code == 404


def test_activate_deactivate_product(client, crud_seed):
    headers = _bearer(client, "admin@example.com")
    category = _create_category(client, headers)
    product = _create_product(client, headers, category["id"]).json()

    response = client.post(f"/api/products/{product['id']}/deactivate", headers=headers)
    assert response.status_code == 200
    assert response.json()["is_active"] is False

    response = client.post(f"/api/products/{product['id']}/activate", headers=headers)
    assert response.status_code == 200
    assert response.json()["is_active"] is True


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------

def test_update_product_partial(client, crud_seed):
    headers = _bearer(client, "admin@example.com")
    category = _create_category(client, headers)
    product = _create_product(client, headers, category["id"]).json()

    response = client.patch(
        f"/api/products/{product['id']}", json={"price": "19.99"}, headers=headers
    )
    assert response.status_code == 200
    body = response.json()
    assert body["price"] == "19.99"
    assert body["name"] == product["name"]  # untouched


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------

def test_delete_product_ok(client, crud_seed):
    headers = _bearer(client, "admin@example.com")
    category = _create_category(client, headers)
    product = _create_product(client, headers, category["id"]).json()

    response = client.delete(f"/api/products/{product['id']}", headers=headers)
    assert response.status_code == 204
    assert client.get(f"/api/products/{product['id']}", headers=headers).status_code == 404


def test_delete_product_forbidden_for_sales(client, crud_seed):
    headers = _bearer(client, "admin@example.com")
    category = _create_category(client, headers)
    product = _create_product(client, headers, category["id"]).json()

    response = client.delete(
        f"/api/products/{product['id']}", headers=_bearer(client, "sales@example.com")
    )
    assert response.status_code == 403
