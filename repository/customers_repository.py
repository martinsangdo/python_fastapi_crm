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

from typing import Optional, Tuple

from sqlalchemy import or_
from sqlalchemy.orm import Session

from models import Customer

# The columns a client is allowed to sort by. We map the public sort name to
# the real model column. Anything not in this dict falls back to "created_at",
# so a bad/unknown sort value can never crash the query or leak internals.
_SORTABLE_COLUMNS = {
    "name": Customer.name,
    "status": Customer.status,
    "created_at": Customer.created_at,
}


def list_customers(
    db: Session,
    *,
    search: Optional[str] = None,
    status: Optional[str] = None,
    owner_id=None,
    sort: str = "created_at",
    order: str = "desc",
    page: int = 1,
    page_size: int = 20,
) -> Tuple[list[Customer], int]:
    """
    Return one page of customers plus the TOTAL number that matched the
    filters.

    Filtering:
      - search:   matches name OR company OR email (case-insensitive, partial).
      - status:   only customers with that exact status.
      - owner_id: only customers owned by that user.

    The total is counted BEFORE paging so the UI can show "page 2 of 7".
    """
    query = db.query(Customer)

    # ---- filters ----------------------------------------------------------
    if search:
        like = f"%{search.strip()}%"
        query = query.filter(
            or_(
                Customer.name.ilike(like),
                Customer.company.ilike(like),
                Customer.email.ilike(like),
            )
        )

    if status is not None:
        query = query.filter(Customer.status == status)

    if owner_id is not None:
        query = query.filter(Customer.owner_id == owner_id)

    # Count the matches before we slice the query into a single page.
    total = query.count()

    # ---- sorting ------------------------------------------------------------
    column = _SORTABLE_COLUMNS.get(sort, Customer.created_at)
    query = query.order_by(column.asc() if order == "asc" else column.desc())

    # ---- paging -------------------------------------------------------------
    # Clamp to sensible bounds so a client cannot ask for page 0 or 10,000 rows.
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)
    rows = query.offset((page - 1) * page_size).limit(page_size).all()

    return rows, total


def get_customer(db: Session, customer_id) -> Optional[Customer]:
    """Load one customer by id (or None if there is no such customer)."""
    return db.query(Customer).filter(Customer.id == customer_id).first()


def add_customer(db: Session, customer: Customer) -> Customer:
    """Persist a brand-new customer and reload it (fills in id/timestamps)."""
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
