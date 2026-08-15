"""
routers/customers.py
---------------------
The HTTP layer of the Customers module: every /api/customers endpoint.

Like routers/users.py, this file stays thin. Each route:
  1. Receives validated input (thanks to the Pydantic schemas).
  2. Is guarded by `require_permission(...)` so only allowed roles get in.
  3. Calls a function in customers_service.py to do the real work.
  4. Turns any typed service error into the matching HTTP status code.

Endpoints:
    GET    /api/customers        -> list (paged/filtered/sorted)
    POST   /api/customers        -> create
    GET    /api/customers/{id}   -> detail
    PATCH  /api/customers/{id}   -> partial update
    DELETE /api/customers/{id}   -> hard delete (blocked if it has orders)
"""

import math
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

import service.customers_service as service
from authorization import require_permission
from schemas.customers_schemas import (
    AddressSummary,
    CustomerCreate,
    CustomerDetail,
    CustomerListItem,
    CustomerListPage,
    CustomerUpdate,
)
from database import get_db
from models import User

router = APIRouter(tags=["customers"])


def _http_from_service_error(error: Exception) -> HTTPException:
    """Map our typed service errors to the right status code."""
    if isinstance(error, service.NotFoundError):
        return HTTPException(status.HTTP_404_NOT_FOUND, detail=str(error))
    if isinstance(error, service.ConflictError):
        return HTTPException(status.HTTP_409_CONFLICT, detail=str(error))
    if isinstance(error, service.BusinessRuleError):
        return HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(error))
    return HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(error))


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------

@router.get("/api/customers", response_model=CustomerListPage)
def list_customers(
    search: Optional[str] = None,
    sort: str = Query("created_at"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    _: User = Depends(require_permission("customers.read")),
    db: Session = Depends(get_db),
):
    """Return a filtered, sorted, paginated page of customers."""
    rows, total = service.list_customers(
        db, search=search, sort=sort, order=order, page=page, page_size=page_size
    )
    total_pages = math.ceil(total / page_size) if total else 0
    return CustomerListPage(
        items=[CustomerListItem.model_validate(c) for c in rows],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

@router.post(
    "/api/customers",
    response_model=CustomerDetail,
    status_code=status.HTTP_201_CREATED,
)
def create_customer(
    data: CustomerCreate,
    _: User = Depends(require_permission("customers.create")),
    db: Session = Depends(get_db),
):
    """Create a new customer and return its full detail view."""
    try:
        customer = service.create_customer(db, data)
    except (service.BusinessRuleError, service.ConflictError) as error:
        raise _http_from_service_error(error)
    return service.to_detail(customer)


# ---------------------------------------------------------------------------
# Detail
# ---------------------------------------------------------------------------

@router.get("/api/customers/{customer_id}", response_model=CustomerDetail)
def get_customer(
    customer_id: int,
    _: User = Depends(require_permission("customers.read")),
    db: Session = Depends(get_db),
):
    """Return one customer."""
    try:
        customer = service.get_customer_or_404(db, customer_id)
    except service.NotFoundError as error:
        raise _http_from_service_error(error)
    return service.to_detail(customer)


# ---------------------------------------------------------------------------
# Addresses (used by the Orders module's shipping-address picker)
# ---------------------------------------------------------------------------

@router.get("/api/customers/{customer_id}/addresses", response_model=List[AddressSummary])
def list_customer_addresses(
    customer_id: int,
    _: User = Depends(require_permission("customers.read")),
    db: Session = Depends(get_db),
):
    """Return a customer's saved shipping addresses."""
    try:
        addresses = service.list_addresses(db, customer_id)
    except service.NotFoundError as error:
        raise _http_from_service_error(error)
    return [AddressSummary.model_validate(a) for a in addresses]


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------

@router.patch("/api/customers/{customer_id}", response_model=CustomerDetail)
def update_customer(
    customer_id: int,
    data: CustomerUpdate,
    _: User = Depends(require_permission("customers.update")),
    db: Session = Depends(get_db),
):
    """Apply a partial update to a customer."""
    try:
        customer = service.update_customer(db, customer_id, data)
    except (service.NotFoundError, service.BusinessRuleError, service.ConflictError) as error:
        raise _http_from_service_error(error)
    return service.to_detail(customer)


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------

@router.delete("/api/customers/{customer_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_customer(
    customer_id: int,
    _: User = Depends(require_permission("customers.delete")),
    db: Session = Depends(get_db),
):
    """Permanently delete a customer (blocked if it has any orders)."""
    try:
        service.delete_customer(db, customer_id)
    except (service.NotFoundError, service.ConflictError) as error:
        raise _http_from_service_error(error)
    return None
