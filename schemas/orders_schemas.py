"""
orders_schemas.py
------------------
Pydantic "schemas" for the Orders module.

These describe the SHAPE of the data going in and out of the /api/orders
API, separately from the SQLAlchemy models in models.py.
"""

from datetime import datetime
from decimal import Decimal
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from schemas.customers_schemas import AddressSummary

# The only statuses an order may have, and the only forward path between
# them. Reused by the schema and the service layer so the allowed set is
# defined in exactly one place.
OrderStatus = Literal["pending", "paid", "shipped", "completed", "cancelled"]


# ---------------------------------------------------------------------------
# Small shared pieces
# ---------------------------------------------------------------------------

class CustomerSummary(BaseModel):
    """A tiny view of the ordering customer — enough to show a name in the UI."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str
    email: str


class ProductSummary(BaseModel):
    """A tiny view of an ordered product — enough to show it on a line item."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    sku: str
    name: str


# ---------------------------------------------------------------------------
# Requests (data coming IN from the browser)
# ---------------------------------------------------------------------------

class OrderItemCreate(BaseModel):
    """One line of an order being created or edited."""

    product_id: int
    quantity: int = Field(gt=0)


class OrderCreate(BaseModel):
    """Body for POST /api/orders."""

    customer_id: int
    shipping_address_id: Optional[int] = None
    items: List[OrderItemCreate] = Field(min_length=1)


class OrderUpdate(BaseModel):
    """
    Body for PATCH /api/orders/{id}.

    Only allowed while the order is still 'pending'. `items`, when given, is
    a FULL REPLACEMENT of the order's line items (not a merge/patch of them).
    """

    shipping_address_id: Optional[int] = None
    items: Optional[List[OrderItemCreate]] = Field(default=None, min_length=1)


class OrderStatusUpdate(BaseModel):
    """Body for POST /api/orders/{id}/status."""

    status: OrderStatus


# ---------------------------------------------------------------------------
# Responses (data going OUT to the browser)
# ---------------------------------------------------------------------------

class OrderItemOut(BaseModel):
    """One line item as shown in an order's detail view."""

    id: int
    product: ProductSummary
    quantity: int
    unit_price: Decimal
    line_total: Decimal


class OrderListItem(BaseModel):
    """One row in the orders list table."""

    id: int
    customer_id: int
    customer_name: str
    status: OrderStatus
    total_amount: Decimal
    item_count: int
    placed_at: datetime


class OrderListPage(BaseModel):
    """A single page of orders, plus the numbers the UI needs for paging."""

    items: List[OrderListItem]
    total: int
    page: int
    page_size: int
    total_pages: int


class OrderDetail(BaseModel):
    """The full view of one order: header, customer, address, and lines."""

    id: int
    customer: CustomerSummary
    status: OrderStatus
    shipping_address: Optional[AddressSummary] = None
    items: List[OrderItemOut]
    total_amount: Decimal
    placed_at: datetime
