"""
tests/test_api_orders.py
--------------------------
API-LAYER tests for the Orders module (/api/orders): the most involved
module, since it composes Customers and Products. Every request goes through
the TestClient with a real bearer token, so routing, permission guards,
schema validation, and the service-error -> HTTP-status mapping are all
exercised together.

Permission model (see conftest.crud_seed):
  * ADMIN holds orders.read/create/update/delete.
  * SALES holds orders.read/create/update (no delete).
"""

from conftest import PASSWORD, login


def _bearer(client, email, password=PASSWORD):
    token = login(client, email, password).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _setup_catalog(client, headers, stock=10, price="10.00"):
    """One category + one active product with the given stock/price."""
    category = client.post("/api/categories", json={"name": "Electronics"}, headers=headers).json()
    product = client.post(
        "/api/products",
        json={
            "category_id": category["id"],
            "sku": "WIDGET-1",
            "name": "Widget",
            "price": price,
            "stock_quantity": stock,
        },
        headers=headers,
    ).json()
    return category, product


def _create_customer(client, headers, email="alice@example.com"):
    return client.post(
        "/api/customers", json={"email": email, "full_name": "Alice Nguyen"}, headers=headers
    ).json()


def _create_order(client, headers, customer_id, product_id, quantity=2):
    return client.post(
        "/api/orders",
        json={"customer_id": customer_id, "items": [{"product_id": product_id, "quantity": quantity}]},
        headers=headers,
    )


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

def test_create_order_requires_authentication(client, crud_seed):
    assert client.post("/api/orders", json={}).status_code == 401


def test_create_order_snapshots_price_and_decrements_stock(client, crud_seed):
    headers = _bearer(client, "admin@example.com")
    _, product = _setup_catalog(client, headers, stock=10, price="10.00")
    customer = _create_customer(client, headers)

    response = _create_order(client, headers, customer["id"], product["id"], quantity=3)
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "pending"
    assert body["total_amount"] == "30.00"
    assert len(body["items"]) == 1
    assert body["items"][0]["unit_price"] == "10.00"
    assert body["items"][0]["line_total"] == "30.00"

    # Stock was decremented server-side.
    product_after = client.get(f"/api/products/{product['id']}", headers=headers).json()
    assert product_after["stock_quantity"] == 7


def test_create_order_insufficient_stock_conflict(client, crud_seed):
    headers = _bearer(client, "admin@example.com")
    _, product = _setup_catalog(client, headers, stock=2)
    customer = _create_customer(client, headers)

    response = _create_order(client, headers, customer["id"], product["id"], quantity=5)
    assert response.status_code == 409
    # Nothing was decremented on the failed attempt.
    product_after = client.get(f"/api/products/{product['id']}", headers=headers).json()
    assert product_after["stock_quantity"] == 2


def test_create_order_inactive_product_rejected(client, crud_seed):
    headers = _bearer(client, "admin@example.com")
    _, product = _setup_catalog(client, headers)
    client.post(f"/api/products/{product['id']}/deactivate", headers=headers)
    customer = _create_customer(client, headers)

    response = _create_order(client, headers, customer["id"], product["id"])
    assert response.status_code == 400


def test_create_order_unknown_customer_404(client, crud_seed):
    headers = _bearer(client, "admin@example.com")
    _, product = _setup_catalog(client, headers)

    response = _create_order(client, headers, customer_id=999999, product_id=product["id"])
    assert response.status_code == 404


def test_create_order_empty_items_422(client, crud_seed):
    headers = _bearer(client, "admin@example.com")
    customer = _create_customer(client, headers)
    response = client.post(
        "/api/orders", json={"customer_id": customer["id"], "items": []}, headers=headers
    )
    assert response.status_code == 422


def test_create_order_duplicate_product_line_rejected(client, crud_seed):
    headers = _bearer(client, "admin@example.com")
    _, product = _setup_catalog(client, headers, stock=10)
    customer = _create_customer(client, headers)

    response = client.post(
        "/api/orders",
        json={
            "customer_id": customer["id"],
            "items": [
                {"product_id": product["id"], "quantity": 1},
                {"product_id": product["id"], "quantity": 1},
            ],
        },
        headers=headers,
    )
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# Status transitions
# ---------------------------------------------------------------------------

def test_status_lifecycle_forward_path(client, crud_seed):
    headers = _bearer(client, "admin@example.com")
    _, product = _setup_catalog(client, headers)
    customer = _create_customer(client, headers)
    order = _create_order(client, headers, customer["id"], product["id"]).json()

    for next_status in ("paid", "shipped", "completed"):
        response = client.post(
            f"/api/orders/{order['id']}/status", json={"status": next_status}, headers=headers
        )
        assert response.status_code == 200
        assert response.json()["status"] == next_status


def test_illegal_status_jump_rejected(client, crud_seed):
    headers = _bearer(client, "admin@example.com")
    _, product = _setup_catalog(client, headers)
    customer = _create_customer(client, headers)
    order = _create_order(client, headers, customer["id"], product["id"]).json()

    response = client.post(
        f"/api/orders/{order['id']}/status", json={"status": "shipped"}, headers=headers
    )
    assert response.status_code == 409


def test_cancel_restocks_product(client, crud_seed):
    headers = _bearer(client, "admin@example.com")
    _, product = _setup_catalog(client, headers, stock=10)
    customer = _create_customer(client, headers)
    order = _create_order(client, headers, customer["id"], product["id"], quantity=4).json()

    assert client.get(f"/api/products/{product['id']}", headers=headers).json()["stock_quantity"] == 6

    response = client.post(
        f"/api/orders/{order['id']}/status", json={"status": "cancelled"}, headers=headers
    )
    assert response.status_code == 200
    assert client.get(f"/api/products/{product['id']}", headers=headers).json()["stock_quantity"] == 10


def test_cancel_completed_order_rejected(client, crud_seed):
    headers = _bearer(client, "admin@example.com")
    _, product = _setup_catalog(client, headers)
    customer = _create_customer(client, headers)
    order = _create_order(client, headers, customer["id"], product["id"]).json()
    for next_status in ("paid", "shipped", "completed"):
        client.post(f"/api/orders/{order['id']}/status", json={"status": next_status}, headers=headers)

    response = client.post(
        f"/api/orders/{order['id']}/status", json={"status": "cancelled"}, headers=headers
    )
    assert response.status_code == 409


# ---------------------------------------------------------------------------
# Update (pending orders only)
# ---------------------------------------------------------------------------

def test_update_order_lines_reconciles_stock(client, crud_seed):
    headers = _bearer(client, "admin@example.com")
    _, product = _setup_catalog(client, headers, stock=10)
    customer = _create_customer(client, headers)
    order = _create_order(client, headers, customer["id"], product["id"], quantity=2).json()
    assert client.get(f"/api/products/{product['id']}", headers=headers).json()["stock_quantity"] == 8

    response = client.patch(
        f"/api/orders/{order['id']}",
        json={"items": [{"product_id": product["id"], "quantity": 5}]},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["total_amount"] == "50.00"
    # 10 - 5 (the new quantity), NOT 10 - 2 - 5.
    assert client.get(f"/api/products/{product['id']}", headers=headers).json()["stock_quantity"] == 5


def test_update_order_forbidden_once_paid(client, crud_seed):
    headers = _bearer(client, "admin@example.com")
    _, product = _setup_catalog(client, headers)
    customer = _create_customer(client, headers)
    order = _create_order(client, headers, customer["id"], product["id"]).json()
    client.post(f"/api/orders/{order['id']}/status", json={"status": "paid"}, headers=headers)

    response = client.patch(
        f"/api/orders/{order['id']}",
        json={"items": [{"product_id": product["id"], "quantity": 1}]},
        headers=headers,
    )
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------

def test_delete_pending_order_restocks(client, crud_seed):
    headers = _bearer(client, "admin@example.com")
    _, product = _setup_catalog(client, headers, stock=10)
    customer = _create_customer(client, headers)
    order = _create_order(client, headers, customer["id"], product["id"], quantity=3).json()

    response = client.delete(f"/api/orders/{order['id']}", headers=headers)
    assert response.status_code == 204
    assert client.get(f"/api/products/{product['id']}", headers=headers).json()["stock_quantity"] == 10


def test_delete_paid_order_rejected(client, crud_seed):
    headers = _bearer(client, "admin@example.com")
    _, product = _setup_catalog(client, headers)
    customer = _create_customer(client, headers)
    order = _create_order(client, headers, customer["id"], product["id"]).json()
    client.post(f"/api/orders/{order['id']}/status", json={"status": "paid"}, headers=headers)

    response = client.delete(f"/api/orders/{order['id']}", headers=headers)
    assert response.status_code == 400


def test_delete_order_forbidden_for_sales(client, crud_seed):
    headers = _bearer(client, "admin@example.com")
    _, product = _setup_catalog(client, headers)
    customer = _create_customer(client, headers)
    order = _create_order(client, headers, customer["id"], product["id"]).json()

    response = client.delete(
        f"/api/orders/{order['id']}", headers=_bearer(client, "sales@example.com")
    )
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# List / filters
# ---------------------------------------------------------------------------

def test_list_orders_filter_by_status(client, crud_seed):
    headers = _bearer(client, "admin@example.com")
    _, product = _setup_catalog(client, headers, stock=20)
    customer = _create_customer(client, headers)
    order = _create_order(client, headers, customer["id"], product["id"]).json()
    client.post(f"/api/orders/{order['id']}/status", json={"status": "paid"}, headers=headers)
    _create_order(client, headers, customer["id"], product["id"])  # stays pending

    response = client.get("/api/orders?status=paid", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["status"] == "paid"


def test_list_orders_search_by_order_id(client, crud_seed):
    headers = _bearer(client, "admin@example.com")
    _, product = _setup_catalog(client, headers, stock=20)
    customer = _create_customer(client, headers)
    order = _create_order(client, headers, customer["id"], product["id"]).json()

    response = client.get(f"/api/orders?search={order['id']}", headers=headers)
    assert response.status_code == 200
    assert response.json()["total"] == 1
