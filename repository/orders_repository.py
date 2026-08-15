"""
orders_repository.py
---------------------
The "data access" layer for the Orders module.

Every function here does ONE thing: talk to the database (through a
SQLAlchemy session) and hand back plain SQLAlchemy objects. There is no
business logic and no HTTP knowledge — same shape as customers_repository.py.
"""

from datetime import datetime
from typing import Optional, Tuple

from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from models import Customer, Order, OrderItem

# The columns a client is allowed to sort by. Anything not in this dict falls
# back to "placed_at", so a bad/unknown sort value can never crash the query.
_SORTABLE_COLUMNS = {
    "placed_at": Order.placed_at,
    "total_amount": Order.total_amount,
    "status": Order.status,
}


def list_orders(
    db: Session,
    *,
    search: Optional[str] = None,
    status: Optional[str] = None,
    customer_id: Optional[int] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    sort: str = "placed_at",
    order: str = "desc",
    page: int = 1,
    page_size: int = 20,
) -> Tuple[list[Order], int]:
    """
    Return one page of orders plus the TOTAL number that matched the filters.

    Filtering:
      - search:      matches the customer's name/email, or an exact order id.
      - status:      only orders with that exact status.
      - customer_id: only orders for that customer.
      - date_from/date_to: inclusive range on placed_at.
    """
    query = db.query(Order).join(Order.customer)

    if search:
        search = search.strip()
        conditions = [
            Customer.full_name.ilike(f"%{search}%"),
            Customer.email.ilike(f"%{search}%"),
        ]
        if search.isdigit():
            conditions.append(Order.id == int(search))
        query = query.filter(or_(*conditions))

    if status is not None:
        query = query.filter(Order.status == status)

    if customer_id is not None:
        query = query.filter(Order.customer_id == customer_id)

    if date_from is not None:
        query = query.filter(Order.placed_at >= date_from)

    if date_to is not None:
        query = query.filter(Order.placed_at <= date_to)

    total = query.count()

    column = _SORTABLE_COLUMNS.get(sort, Order.placed_at)
    query = query.order_by(column.asc() if order == "asc" else column.desc())

    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)
    rows = (
        query.options(joinedload(Order.customer), joinedload(Order.items))
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return rows, total


def get_order(db: Session, order_id) -> Optional[Order]:
    """Load one order, with its customer/address/items+products eager-loaded."""
    return (
        db.query(Order)
        .options(
            joinedload(Order.customer),
            joinedload(Order.shipping_address),
            joinedload(Order.items).joinedload(OrderItem.product),
        )
        .filter(Order.id == order_id)
        .first()
    )


def add_order(db: Session, order: Order) -> Order:
    """
    Persist a brand-new order (and its attached items, via cascade) in ONE
    transaction, and reload it (fills in id/placed_at).
    """
    db.add(order)
    db.commit()
    db.refresh(order)
    return order


def save(db: Session, order: Order) -> Order:
    """
    Write pending changes on an order (and any product stock adjustments made
    on the same session) back to the database in ONE transaction.
    """
    db.commit()
    db.refresh(order)
    return order


def delete_order(db: Session, order: Order) -> None:
    """Permanently remove an order row (its items cascade-delete with it)."""
    db.delete(order)
    db.commit()
