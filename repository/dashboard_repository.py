"""
dashboard_repository.py
------------------------
The "data access" layer for the Dashboard module.

Same shape as the other repositories (e.g. orders_repository.py): every
function talks to the database through a SQLAlchemy session and hands back
plain rows or SQLAlchemy objects. There is no business logic and no chart
formatting here — that happens in service/dashboard_service.py.
"""

from datetime import datetime
from decimal import Decimal
from typing import List, Sequence, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from models import Customer, Order, OrderItem, Product, Category

# Orders in this status never happened financially, so revenue figures
# exclude them everywhere in this module.
_CANCELLED = "cancelled"


def count_customers(db: Session) -> int:
    return db.query(func.count(Customer.id)).scalar() or 0


def count_products(db: Session) -> int:
    return db.query(func.count(Product.id)).scalar() or 0


def count_orders(db: Session) -> int:
    return db.query(func.count(Order.id)).scalar() or 0


def total_revenue(db: Session) -> Decimal:
    """Sum of total_amount across every non-cancelled order."""
    result = (
        db.query(func.coalesce(func.sum(Order.total_amount), 0))
        .filter(Order.status != _CANCELLED)
        .scalar()
    )
    return Decimal(result)


def orders_by_status(db: Session) -> List[Tuple[str, int]]:
    """How many orders currently sit in each status."""
    rows = (
        db.query(Order.status, func.count(Order.id))
        .group_by(Order.status)
        .all()
    )
    return [(status, count) for status, count in rows]


def orders_since(db: Session, since: datetime) -> List[Tuple[datetime, Decimal]]:
    """placed_at + total_amount for every non-cancelled order placed since `since`."""
    rows = (
        db.query(Order.placed_at, Order.total_amount)
        .filter(Order.status != _CANCELLED, Order.placed_at >= since)
        .all()
    )
    return [(placed_at, amount) for placed_at, amount in rows]


def customers_since(db: Session, since: datetime) -> List[datetime]:
    """created_at for every customer created since `since`."""
    rows = (
        db.query(Customer.created_at)
        .filter(Customer.created_at >= since)
        .all()
    )
    return [created_at for (created_at,) in rows]


def top_products_by_revenue(db: Session, limit: int = 5) -> List[Tuple[str, int, Decimal]]:
    """The best-selling products by revenue (quantity * unit_price), excluding
    line items that belong to a cancelled order."""
    rows = (
        db.query(
            Product.name,
            func.coalesce(func.sum(OrderItem.quantity), 0),
            func.coalesce(func.sum(OrderItem.quantity * OrderItem.unit_price), 0),
        )
        .join(OrderItem, OrderItem.product_id == Product.id)
        .join(Order, Order.id == OrderItem.order_id)
        .filter(Order.status != _CANCELLED)
        .group_by(Product.id, Product.name)
        .order_by(func.sum(OrderItem.quantity * OrderItem.unit_price).desc())
        .limit(limit)
        .all()
    )
    return [(name, int(qty), Decimal(revenue)) for name, qty, revenue in rows]


def products_by_category(db: Session) -> List[Tuple[str, int]]:
    """How many products sit in each category, most-populated first."""
    rows = (
        db.query(Category.name, func.count(Product.id))
        .join(Product, Product.category_id == Category.id)
        .group_by(Category.id, Category.name)
        .order_by(func.count(Product.id).desc())
        .all()
    )
    return [(name, count) for name, count in rows]


def low_stock_products(db: Session, threshold: int = 10, limit: int = 5) -> List[Tuple[str, int]]:
    """Active products with the least stock left, worth restocking first."""
    rows = (
        db.query(Product.name, Product.stock_quantity)
        .filter(Product.is_active.is_(True), Product.stock_quantity <= threshold)
        .order_by(Product.stock_quantity.asc())
        .limit(limit)
        .all()
    )
    return [(name, qty) for name, qty in rows]
