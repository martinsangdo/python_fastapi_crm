"""
customers_service.py
---------------------
The "business logic" of the Customers module.

These functions enforce the module's RULES (required name, unique email,
delete blocked while orders still reference the customer) and talk to the
database through customers_repository.py. They know NOTHING about HTTP —
instead they raise clear, typed errors that the router turns into the right
status code (the same pattern as users_service.py):
  * NotFoundError      -> the router returns 404
  * BusinessRuleError  -> the router returns 400 (e.g. an empty name)
  * ConflictError      -> the router returns 409 (duplicate email, or a
                           delete blocked by existing orders)
"""

from typing import Optional

from sqlalchemy.orm import Session

import repository.customers_repository as repo
from models import Customer
from schemas.customers_schemas import CustomerCreate, CustomerDetail, CustomerUpdate


# ---------------------------------------------------------------------------
# Typed errors — the router maps each of these to an HTTP status code.
# ---------------------------------------------------------------------------

class NotFoundError(Exception):
    """Raised when the requested customer does not exist."""


class BusinessRuleError(Exception):
    """Raised when a request is understood but breaks a module rule."""


class ConflictError(Exception):
    """Raised on a duplicate email, or deleting a customer with orders."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def to_detail(customer: Customer) -> CustomerDetail:
    """Build the full detail view of a customer."""
    return CustomerDetail(
        id=customer.id,
        email=customer.email,
        full_name=customer.full_name,
        created_at=customer.created_at,
    )


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------

def get_customer_or_404(db: Session, customer_id) -> Customer:
    """Load a customer, or raise NotFoundError if there is none with that id."""
    customer = repo.get_customer(db, customer_id)
    if customer is None:
        raise NotFoundError("Customer not found.")
    return customer


def list_customers(
    db: Session,
    *,
    search: Optional[str],
    sort: str,
    order: str,
    page: int,
    page_size: int,
):
    """Return (rows, total) for a page of customers. Filtering lives in the repo."""
    return repo.list_customers(
        db, search=search, sort=sort, order=order, page=page, page_size=page_size
    )


def list_addresses(db: Session, customer_id):
    """A customer's saved shipping addresses (used by the Orders module)."""
    get_customer_or_404(db, customer_id)
    return repo.list_addresses(db, customer_id)


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

def create_customer(db: Session, data: CustomerCreate) -> Customer:
    """
    Create a customer.

    The full name is trimmed and must be non-empty (Pydantic's min_length
    already rejects an empty string, but a whitespace-only one would slip
    through). The email is lowercased and must be unique.
    """
    full_name = data.full_name.strip()
    if not full_name:
        raise BusinessRuleError("Full name is required.")

    email = data.email.lower()
    if repo.get_customer_by_email(db, email) is not None:
        raise ConflictError(f"A customer with email '{email}' already exists.")

    customer = Customer(email=email, full_name=full_name)
    return repo.add_customer(db, customer)


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------

def update_customer(db: Session, customer_id, data: CustomerUpdate) -> Customer:
    """
    Apply a partial update to a customer.

    Only the fields actually sent are touched (Pydantic's exclude_unset). If
    the email changes, uniqueness is re-checked.
    """
    customer = get_customer_or_404(db, customer_id)
    changes = data.model_dump(exclude_unset=True)

    if "full_name" in changes:
        full_name = (changes["full_name"] or "").strip()
        if not full_name:
            raise BusinessRuleError("Full name is required.")
        customer.full_name = full_name

    if "email" in changes:
        email = (changes["email"] or "").lower()
        if not email:
            raise BusinessRuleError("Email is required.")
        if email != customer.email and repo.get_customer_by_email(db, email) is not None:
            raise ConflictError(f"A customer with email '{email}' already exists.")
        customer.email = email

    return repo.save(db, customer)


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------

def delete_customer(db: Session, customer_id) -> None:
    """
    Permanently remove a customer.

    Blocked (409) while any order still references it — matches the
    database's own ON DELETE RESTRICT foreign key.
    """
    customer = get_customer_or_404(db, customer_id)
    in_use = repo.count_orders(db, customer_id)
    if in_use > 0:
        raise ConflictError(
            f"Cannot delete '{customer.full_name}': {in_use} order(s) still reference this customer."
        )
    repo.delete_customer(db, customer)
