"""
orders_service.py
------------------
The "business logic" of the Orders module — the most involved module in the
app, since it composes Customers and Products.

These functions enforce the module's RULES and talk to the database through
orders_repository.py (plus customers_repository.py / products_repository.py
for cross-module lookups). They know NOTHING about HTTP — instead they raise
clear, typed errors that the router turns into the right status code:
  * NotFoundError      -> the router returns 404 (unknown order/customer/
                           product/address)
  * BusinessRuleError  -> the router returns 400 (empty order, inactive
                           product, editing a locked order, ...)
  * ConflictError      -> the router returns 409 (insufficient stock, an
                           illegal status transition, deleting a locked order)

Business rules (see docs/04_orders_module_prompt.txt for the original spec —
adapted here to the plain `orders`/`order_items` tables that already existed
in this Supabase project, which have no order_number/currency/subtotal/notes
columns):
  - An order must have at least one line item; each quantity > 0.
  - unit_price is a SNAPSHOT of the product's price at order time — it never
    changes if the catalog price changes later.
  - Only is_active products can be added to a new or edited order.
  - Creating/expanding an order decrements product stock_quantity and must
    not drive it below 0 (insufficient stock -> 409). Cancelling or deleting
    a pending order restocks it.
  - total_amount is always recomputed server-side from the line items.
  - Status lifecycle: pending -> paid -> shipped -> completed (one step at a
    time); any of pending/paid/shipped -> cancelled. Illegal jumps are
    rejected (409).
  - Line items and the shipping address are editable only while the order is
    'pending'.
  - Deletion is allowed only for 'pending' or 'cancelled' orders.
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

import repository.customers_repository as customers_repo
import repository.orders_repository as repo
import repository.products_repository as products_repo
from models import Order, OrderItem
from schemas.customers_schemas import AddressSummary
from schemas.orders_schemas import (
    CustomerSummary,
    OrderCreate,
    OrderDetail,
    OrderItemCreate,
    OrderItemOut,
    OrderListItem,
    OrderUpdate,
    ProductSummary,
)


# ---------------------------------------------------------------------------
# Typed errors — the router maps each of these to an HTTP status code.
# ---------------------------------------------------------------------------

class NotFoundError(Exception):
    """Raised when the order, customer, product, or address does not exist."""


class BusinessRuleError(Exception):
    """Raised when a request is understood but breaks a module rule."""


class ConflictError(Exception):
    """Raised on insufficient stock, an illegal status change, or a delete/
    edit blocked by the order's current status."""


# The only forward step allowed from a given status (cancellation is handled
# separately, since it can happen from several non-terminal statuses).
_FORWARD_TRANSITIONS = {
    "pending": "paid",
    "paid": "shipped",
    "shipped": "completed",
}
_CANCELLABLE_FROM = {"pending", "paid", "shipped"}
_ALLOWED_STATUSES = {"pending", "paid", "shipped", "completed", "cancelled"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def to_detail(order: Order) -> OrderDetail:
    """Build the full detail view of an order: header, customer, address, lines."""
    return OrderDetail(
        id=order.id,
        customer=CustomerSummary.model_validate(order.customer),
        status=order.status,
        shipping_address=(
            AddressSummary.model_validate(order.shipping_address)
            if order.shipping_address is not None
            else None
        ),
        items=[
            OrderItemOut(
                id=item.id,
                product=ProductSummary.model_validate(item.product),
                quantity=item.quantity,
                unit_price=item.unit_price,
                line_total=item.unit_price * item.quantity,
            )
            for item in order.items
        ],
        total_amount=order.total_amount,
        placed_at=order.placed_at,
    )


def to_list_item(order: Order) -> OrderListItem:
    """Build one summary row for the orders list table."""
    return OrderListItem(
        id=order.id,
        customer_id=order.customer_id,
        customer_name=order.customer.full_name,
        status=order.status,
        total_amount=order.total_amount,
        item_count=len(order.items),
        placed_at=order.placed_at,
    )


def _resolve_shipping_address(db: Session, customer_id, address_id):
    """Raise NotFoundError/BusinessRuleError unless address_id is a real
    address belonging to this customer (None is always fine — no address)."""
    if address_id is None:
        return None
    address = customers_repo.get_address(db, address_id)
    if address is None:
        raise NotFoundError("The selected shipping address does not exist.")
    if address.customer_id != customer_id:
        raise BusinessRuleError("That address does not belong to this customer.")
    return address


def _build_items(db: Session, item_inputs: list[OrderItemCreate]) -> list[OrderItem]:
    """
    Validate each requested line (product exists, is active, has enough
    stock), decrement stock in-memory, and return new OrderItem objects with
    price snapshotted from the current catalog. Nothing is committed here —
    the caller commits everything (order + item rows + stock changes) in one
    transaction.
    """
    seen_product_ids = set()
    items: list[OrderItem] = []

    for line in item_inputs:
        if line.product_id in seen_product_ids:
            raise BusinessRuleError(
                "Each product can only appear once per order — combine the quantities."
            )
        seen_product_ids.add(line.product_id)

        product = products_repo.get_product(db, line.product_id)
        if product is None:
            raise NotFoundError(f"Product {line.product_id} does not exist.")
        if not product.is_active:
            raise BusinessRuleError(f"Product '{product.name}' is not active.")
        if product.stock_quantity < line.quantity:
            raise ConflictError(
                f"Insufficient stock for '{product.name}': "
                f"{product.stock_quantity} available, {line.quantity} requested."
            )

        product.stock_quantity -= line.quantity
        items.append(
            OrderItem(
                product_id=product.id,
                quantity=line.quantity,
                unit_price=product.price,
            )
        )

    return items


def _restock(db: Session, items: list[OrderItem]) -> None:
    """Give stock back to the products on an order being cancelled/deleted/edited."""
    for item in items:
        product = products_repo.get_product(db, item.product_id)
        if product is not None:
            product.stock_quantity += item.quantity


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------

def get_order_or_404(db: Session, order_id) -> Order:
    """Load an order, or raise NotFoundError if there is none with that id."""
    order = repo.get_order(db, order_id)
    if order is None:
        raise NotFoundError("Order not found.")
    return order


def list_orders(
    db: Session,
    *,
    search: Optional[str],
    status: Optional[str],
    customer_id: Optional[int],
    date_from: Optional[datetime],
    date_to: Optional[datetime],
    sort: str,
    order: str,
    page: int,
    page_size: int,
):
    """Return (rows, total) for a page of orders. Filtering lives in the repo."""
    return repo.list_orders(
        db,
        search=search,
        status=status,
        customer_id=customer_id,
        date_from=date_from,
        date_to=date_to,
        sort=sort,
        order=order,
        page=page,
        page_size=page_size,
    )


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

def create_order(db: Session, data: OrderCreate) -> Order:
    """
    Create a new order: validate the customer, address, and every line item,
    snapshot prices, decrement stock, and compute the total — all in ONE
    transaction (a single commit at the end).
    """
    if customers_repo.get_customer(db, data.customer_id) is None:
        raise NotFoundError("Customer not found.")

    _resolve_shipping_address(db, data.customer_id, data.shipping_address_id)

    items = _build_items(db, data.items)
    total_amount = sum((item.unit_price * item.quantity for item in items), Decimal("0"))

    order = Order(
        customer_id=data.customer_id,
        shipping_address_id=data.shipping_address_id,
        status="pending",
        total_amount=total_amount,
        items=items,
    )
    order = repo.add_order(db, order)
    return repo.get_order(db, order.id)


# ---------------------------------------------------------------------------
# Update (shipping address / line items — pending orders only)
# ---------------------------------------------------------------------------

def update_order(db: Session, order_id, data: OrderUpdate) -> Order:
    """
    Update an order's shipping address and/or fully replace its line items.

    Only allowed while the order is still 'pending' — once it has moved
    forward (paid/shipped/completed) or been cancelled, it is immutable
    except via change_status().
    """
    order = get_order_or_404(db, order_id)
    if order.status != "pending":
        raise BusinessRuleError(
            f"Cannot edit an order in '{order.status}' status; only pending orders can be edited."
        )

    changes = data.model_dump(exclude_unset=True)

    if "shipping_address_id" in changes:
        _resolve_shipping_address(db, order.customer_id, changes["shipping_address_id"])
        order.shipping_address_id = changes["shipping_address_id"]

    if "items" in changes:
        # Give back the stock the current lines are holding, replace the
        # lines, then re-validate/re-reserve stock for the new ones. Flush
        # the deletion immediately so re-adding the same product in the new
        # set can't collide with the old row on (order_id, product_id).
        _restock(db, order.items)
        order.items.clear()
        db.flush()

        new_items = _build_items(db, data.items)
        order.items.extend(new_items)
        order.total_amount = sum(
            (item.unit_price * item.quantity for item in order.items), Decimal("0")
        )

    order = repo.save(db, order)
    return repo.get_order(db, order.id)


# ---------------------------------------------------------------------------
# Status changes
# ---------------------------------------------------------------------------

def change_status(db: Session, order_id, new_status: str) -> Order:
    """
    Move an order to a new status, enforcing the allowed lifecycle:
        pending -> paid -> shipped -> completed
        (pending | paid | shipped) -> cancelled
    Cancelling restocks the order's items; any other illegal jump is a 409.
    """
    order = get_order_or_404(db, order_id)

    if new_status not in _ALLOWED_STATUSES:
        raise BusinessRuleError(f"Unknown status '{new_status}'.")

    if new_status == order.status:
        return order

    if new_status == "cancelled":
        if order.status not in _CANCELLABLE_FROM:
            raise ConflictError(f"Cannot cancel an order that is already '{order.status}'.")
        _restock(db, order.items)
        order.status = "cancelled"
    elif _FORWARD_TRANSITIONS.get(order.status) == new_status:
        order.status = new_status
    else:
        raise ConflictError(
            f"Cannot change status from '{order.status}' to '{new_status}'."
        )

    order = repo.save(db, order)
    return repo.get_order(db, order.id)


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------

def delete_order(db: Session, order_id) -> None:
    """
    Permanently remove an order.

    Only 'pending' or 'cancelled' orders can be deleted (others must be
    cancelled first, to preserve financial history). A pending order's stock
    is given back; a cancelled order's stock was already restored when it
    was cancelled, so it is not restocked twice.
    """
    order = get_order_or_404(db, order_id)
    if order.status == "pending":
        _restock(db, order.items)
    elif order.status != "cancelled":
        raise BusinessRuleError(
            f"Cannot delete an order in '{order.status}' status; cancel it first."
        )
    repo.delete_order(db, order)
