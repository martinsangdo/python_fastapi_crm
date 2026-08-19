"""
daily_summary_repository.py
------------------------------
The "data access" layer for the daily summary email. Same shape as
dashboard_repository.py: every function talks to the database through a
SQLAlchemy session and hands back plain values — no business logic, no AI,
no email sending.
"""

from datetime import datetime
from decimal import Decimal
from typing import List, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from models import Order, OrderItem, Product

# Orders in this status never happened financially, so they are excluded
# from every query below (same rule as dashboard_repository.py).
_CANCELLED = "cancelled"


def sales_between(db: Session, start: datetime, end: datetime) -> Tuple[Decimal, int]:
    """Total revenue + order count for non-cancelled orders placed in [start, end)."""
    revenue, count = (
        db.query(
            func.coalesce(func.sum(Order.total_amount), 0),
            func.count(Order.id),
        )
        .filter(
            Order.status != _CANCELLED,
            Order.placed_at >= start,
            Order.placed_at < end,
        )
        .first()
    )
    return Decimal(revenue), int(count)


def top_selling_products_between(
    db: Session, start: datetime, end: datetime, limit: int = 3
) -> List[Tuple[str, int, Decimal]]:
    """The products sold the most (by quantity) in [start, end), excluding
    line items that belong to a cancelled order."""
    rows = (
        db.query(
            Product.name,
            func.coalesce(func.sum(OrderItem.quantity), 0),
            func.coalesce(func.sum(OrderItem.quantity * OrderItem.unit_price), 0),
        )
        .join(OrderItem, OrderItem.product_id == Product.id)
        .join(Order, Order.id == OrderItem.order_id)
        .filter(
            Order.status != _CANCELLED,
            Order.placed_at >= start,
            Order.placed_at < end,
        )
        .group_by(Product.id, Product.name)
        .order_by(func.sum(OrderItem.quantity).desc())
        .limit(limit)
        .all()
    )
    return [(name, int(qty), Decimal(revenue)) for name, qty, revenue in rows]
