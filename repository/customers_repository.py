"""
customers_repository.py
------------------------
The "data access" layer for the Customers module.

Every function here does ONE thing: talk to the database (through a
SQLAlchemy session) and hand back plain SQLAlchemy objects. There is no
business logic and no HTTP knowledge — that keeps these functions tiny and
easy to reuse.

The service layer (customers_service.py) calls into this file; the router
calls the service. Keeping the layers separate is what makes the code easy
to follow (the same pattern as users_repository.py).
"""

from datetime import datetime
from typing import Optional, Tuple

from sqlalchemy import or_
from sqlalchemy.orm import Session

from models import Address, Customer, Order

# The columns a client is allowed to sort by. We map the public sort name to
# the real model column. Anything not in this dict falls back to "created_at",
# so a bad/unknown sort value can never crash the query or leak internals.
_SORTABLE_COLUMNS = {
    "full_name": Customer.full_name,
    "email": Customer.email,
    "created_at": Customer.created_at,
}


def list_customers(
    db: Session,
    *,
    search: Optional[str] = None,
    sort: str = "created_at",
    order: str = "desc",
    page: int = 1,
    page_size: int = 20,
) -> Tuple[list[Customer], int]:
    """
    Return one page of customers plus the TOTAL number that matched the
    filters.

    Filtering:
      - search: matches full_name OR email (case-insensitive, partial).

    The total is counted BEFORE paging so the UI can show "page 2 of 7".
    """
    query = db.query(Customer)

    if search:
        like = f"%{search.strip()}%"
        query = query.filter(
            or_(Customer.full_name.ilike(like), Customer.email.ilike(like))
        )

    total = query.count()

    column = _SORTABLE_COLUMNS.get(sort, Customer.created_at)
    query = query.order_by(column.asc() if order == "asc" else column.desc())

    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)
    rows = query.offset((page - 1) * page_size).limit(page_size).all()

    return rows, total


def get_customer(db: Session, customer_id) -> Optional[Customer]:
    """Load one customer by id (or None if there is no such customer)."""
    return db.query(Customer).filter(Customer.id == customer_id).first()


def get_customer_by_email(db: Session, email: str) -> Optional[Customer]:
    """Look up a customer by their unique email (used to check for duplicates)."""
    return db.query(Customer).filter(Customer.email == email).first()


def list_created_between(
    db: Session, start: datetime, end: datetime
) -> list[Customer]:
    """
    Customers created in [start, end) — used by the daily "new customers
    today" check (service/customer_care_service.py). `start`/`end` should be
    timezone-aware to match the timezone-aware `created_at` column.
    """
    return (
        db.query(Customer)
        .filter(Customer.created_at >= start, Customer.created_at < end)
        .order_by(Customer.created_at.asc())
        .all()
    )


def count_orders(db: Session, customer_id) -> int:
    """How many orders still reference this customer (blocks delete if > 0)."""
    return db.query(Order).filter(Order.customer_id == customer_id).count()


def list_addresses(db: Session, customer_id) -> list[Address]:
    """A customer's saved shipping addresses (used by the Orders module)."""
    return (
        db.query(Address)
        .filter(Address.customer_id == customer_id)
        .order_by(Address.is_default.desc(), Address.id.asc())
        .all()
    )


def get_address(db: Session, address_id) -> Optional[Address]:
    """Load one address by id (used to validate an order's shipping address)."""
    return db.query(Address).filter(Address.id == address_id).first()


def add_customer(db: Session, customer: Customer) -> Customer:
    """Persist a brand-new customer and reload it (fills in id/created_at)."""
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return customer


def save(db: Session, customer: Customer) -> Customer:
    """Write pending changes on an existing customer back to the database."""
    db.commit()
    db.refresh(customer)
    return customer


def delete_customer(db: Session, customer: Customer) -> None:
    """Permanently remove a customer row (a hard delete)."""
    db.delete(customer)
    db.commit()
