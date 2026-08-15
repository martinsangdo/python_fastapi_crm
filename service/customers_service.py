"""
customers_service.py
---------------------
The "business logic" of the Customers module.

These functions enforce the module's RULES (required name, allowed statuses,
owner defaulting, ...) and talk to the database through
customers_repository.py. They know NOTHING about HTTP — instead they raise
clear, typed errors that the router turns into the right status code.

Two error types keep that mapping simple and readable (the same pattern as
users_service.py):
  * NotFoundError      -> the router returns 404
  * BusinessRuleError  -> the router returns 400 (e.g. an unknown owner)

Note: the spec's delete guard ("block deleting a customer that has orders")
only applies once the Orders module exists. There is no Order model yet, so
deletion is unconditionally allowed for now — see docs/02_customers_module_prompt.txt §6.
"""

from typing import Optional

from sqlalchemy.orm import Session

import repository.customers_repository as repo
import repository.users_repository as users_repo
from models import Customer, User
from schemas.customers_schemas import CustomerCreate, CustomerDetail, CustomerUpdate, OwnerSummary


# ---------------------------------------------------------------------------
# Typed errors — the router maps each of these to an HTTP status code.
# ---------------------------------------------------------------------------

class NotFoundError(Exception):
    """Raised when the requested customer (or owner) does not exist."""


class BusinessRuleError(Exception):
    """Raised when a request is understood but breaks a module rule."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def to_detail(customer: Customer) -> CustomerDetail:
    """Build the full detail view of a customer, including its owner summary."""
    owner = OwnerSummary.model_validate(customer.owner) if customer.owner is not None else None
    return CustomerDetail(
        id=customer.id,
        name=customer.name,
        email=customer.email,
        phone=customer.phone,
        company=customer.company,
        status=customer.status,
        address_line=customer.address_line,
        city=customer.city,
        country=customer.country,
        notes=customer.notes,
        owner=owner,
        created_at=customer.created_at,
        updated_at=customer.updated_at,
    )


def _resolve_owner(db: Session, owner_id) -> None:
    """Raise NotFoundError if a (non-null) owner_id does not point at a real user."""
    if owner_id is not None and users_repo.get_user(db, owner_id) is None:
        raise NotFoundError("The selected owner does not exist.")


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
    status: Optional[str],
    owner_id,
    sort: str,
    order: str,
    page: int,
    page_size: int,
):
    """Return (rows, total) for a page of customers. Filtering lives in the repo."""
    return repo.list_customers(
        db,
        search=search,
        status=status,
        owner_id=owner_id,
        sort=sort,
        order=order,
        page=page,
        page_size=page_size,
    )


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

def create_customer(db: Session, actor: User, data: CustomerCreate) -> Customer:
    """
    Create a customer on behalf of the logged-in user.

    The name is trimmed and must be non-empty (Pydantic's min_length already
    rejects an empty string, but a whitespace-only one would slip through).
    The email, if given, is lowercased. The owner defaults to the creating
    user when none is given.
    """
    name = data.name.strip()
    if not name:
        raise BusinessRuleError("Name is required.")

    owner_id = data.owner_id if data.owner_id is not None else actor.id
    _resolve_owner(db, owner_id)

    customer = Customer(
        name=name,
        email=data.email.lower() if data.email else None,
        phone=data.phone,
        company=data.company,
        status=data.status,
        address_line=data.address_line,
        city=data.city,
        country=data.country,
        notes=data.notes,
        owner_id=owner_id,
        created_by=actor.id,
    )
    return repo.add_customer(db, customer)


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------

def update_customer(db: Session, customer_id, data: CustomerUpdate) -> Customer:
    """
    Apply a partial update to a customer.

    Only the fields actually sent are touched (Pydantic's exclude_unset), so
    e.g. leaving `owner_id` out keeps the current owner, while sending
    `owner_id: null` clears it.
    """
    customer = get_customer_or_404(db, customer_id)
    changes = data.model_dump(exclude_unset=True)

    if "name" in changes:
        name = (changes["name"] or "").strip()
        if not name:
            raise BusinessRuleError("Name is required.")
        customer.name = name

    if "owner_id" in changes:
        _resolve_owner(db, changes["owner_id"])
        customer.owner_id = changes["owner_id"]

    if "email" in changes:
        customer.email = changes["email"].lower() if changes["email"] else None

    for field in (
        "phone", "company", "status", "address_line", "city", "country", "notes",
    ):
        if field in changes:
            setattr(customer, field, changes[field])

    return repo.save(db, customer)


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------

def delete_customer(db: Session, customer_id) -> None:
    """
    Permanently remove a customer.

    No dependent-orders guard yet: the Orders module does not exist in this
    scaffold, so there is nothing to block deletion on (see module docstring).
    """
    customer = get_customer_or_404(db, customer_id)
    repo.delete_customer(db, customer)
