"""
tests/test_api_customers.py
-----------------------------
API-LAYER tests for the Customers module (/api/customers), which points at
the plain `customers` table (id, email, full_name, created_at — no owner/
status/company fields). Every request goes through the TestClient with a
real bearer token, so routing, permission guards, schema validation, and the
service-error -> HTTP-status mapping are all exercised together.

Permission model (see conftest.crud_seed):
  * ADMIN holds customers.read/create/update/delete.
  * SALES holds customers.read/create/update (no delete).
"""

from conftest import PASSWORD, login


def _bearer(client, email, password=PASSWORD):
    token = login(client, email, password).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _create_customer(client, headers, email="alice@example.com", full_name="Alice Nguyen"):
    return client.post(
        "/api/customers", json={"email": email, "full_name": full_name}, headers=headers
    )


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------

def test_list_customers_requires_authentication(client, crud_seed):
    assert client.get("/api/customers").status_code == 401


def test_list_customers_search(client, crud_seed):
    headers = _bearer(client, "admin@example.com")
    _create_customer(client, headers, "alice@example.com", "Alice Nguyen")
    _create_customer(client, headers, "bob@example.com", "Bob Tran")

    response = client.get("/api/customers?search=bob", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["full_name"] == "Bob Tran"


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

def test_create_customer_ok(client, crud_seed):
    headers = _bearer(client, "admin@example.com")
    response = _create_customer(client, headers)
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "alice@example.com"
    assert body["full_name"] == "Alice Nguyen"
    assert "created_at" in body


def test_create_customer_duplicate_email_conflict(client, crud_seed):
    headers = _bearer(client, "admin@example.com")
    _create_customer(client, headers, "dup@example.com")
    response = _create_customer(client, headers, "dup@example.com", "Someone Else")
    assert response.status_code == 409


def test_create_customer_invalid_email_422(client, crud_seed):
    headers = _bearer(client, "admin@example.com")
    response = client.post(
        "/api/customers", json={"email": "not-an-email", "full_name": "X"}, headers=headers
    )
    assert response.status_code == 422


def test_create_customer_allowed_for_sales(client, crud_seed):
    response = _create_customer(client, _bearer(client, "sales@example.com"))
    assert response.status_code == 201


# ---------------------------------------------------------------------------
# Detail
# ---------------------------------------------------------------------------

def test_get_customer_not_found(client, crud_seed):
    response = client.get("/api/customers/999999", headers=_bearer(client, "admin@example.com"))
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Addresses (used by the Orders module's shipping-address picker)
# ---------------------------------------------------------------------------

def test_list_customer_addresses_empty(client, crud_seed):
    headers = _bearer(client, "admin@example.com")
    customer = _create_customer(client, headers).json()

    response = client.get(f"/api/customers/{customer['id']}/addresses", headers=headers)
    assert response.status_code == 200
    assert response.json() == []


def test_list_addresses_unknown_customer_404(client, crud_seed):
    response = client.get(
        "/api/customers/999999/addresses", headers=_bearer(client, "admin@example.com")
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------

def test_update_customer_partial(client, crud_seed):
    headers = _bearer(client, "admin@example.com")
    customer = _create_customer(client, headers).json()

    response = client.patch(
        f"/api/customers/{customer['id']}", json={"full_name": "Alice N."}, headers=headers
    )
    assert response.status_code == 200
    body = response.json()
    assert body["full_name"] == "Alice N."
    assert body["email"] == customer["email"]  # untouched


def test_update_customer_email_conflict(client, crud_seed):
    headers = _bearer(client, "admin@example.com")
    _create_customer(client, headers, "one@example.com", "One")
    two = _create_customer(client, headers, "two@example.com", "Two").json()

    response = client.patch(
        f"/api/customers/{two['id']}", json={"email": "one@example.com"}, headers=headers
    )
    assert response.status_code == 409


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------

def test_delete_customer_ok(client, crud_seed):
    headers = _bearer(client, "admin@example.com")
    customer = _create_customer(client, headers).json()

    response = client.delete(f"/api/customers/{customer['id']}", headers=headers)
    assert response.status_code == 204
    assert client.get(f"/api/customers/{customer['id']}", headers=headers).status_code == 404


def test_delete_customer_forbidden_for_sales(client, crud_seed):
    headers = _bearer(client, "admin@example.com")
    customer = _create_customer(client, headers).json()

    response = client.delete(
        f"/api/customers/{customer['id']}", headers=_bearer(client, "sales@example.com")
    )
    assert response.status_code == 403


def test_delete_customer_blocked_when_orders_reference_it(client, crud_seed):
    headers = _bearer(client, "admin@example.com")
    customer = _create_customer(client, headers).json()
    category = client.post("/api/categories", json={"name": "Books"}, headers=headers).json()
    product = client.post(
        "/api/products",
        json={"category_id": category["id"], "sku": "B-1", "name": "Book", "price": "5.00", "stock_quantity": 10},
        headers=headers,
    ).json()
    client.post(
        "/api/orders",
        json={"customer_id": customer["id"], "items": [{"product_id": product["id"], "quantity": 1}]},
        headers=headers,
    )

    response = client.delete(f"/api/customers/{customer['id']}", headers=headers)
    assert response.status_code == 409
