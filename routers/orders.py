"""
routers/orders.py
------------------
The HTTP layer of the Orders module: every /api/orders endpoint.

Like routers/customers.py, this file stays thin. Each route:
  1. Receives validated input (thanks to the Pydantic schemas).
  2. Is guarded by `require_permission(...)` so only allowed roles get in.
  3. Calls a function in orders_service.py to do the real work.
  4. Turns any typed service error into the matching HTTP status code.

Endpoints:
    GET    /api/orders               -> list (paged/filtered/sorted)
    POST   /api/orders                -> create (validates stock, snapshots prices)
    GET    /api/orders/{id}           -> detail (customer + address + line items)
    PATCH  /api/orders/{id}           -> edit address/lines (pending orders only)
    POST   /api/orders/{id}/status    -> move to a new lifecycle status
    DELETE /api/orders/{id}           -> delete (pending/cancelled orders only)
"""

import math
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

import service.orders_service as service
from authorization import require_permission
from schemas.orders_schemas import (
    OrderCreate,
    OrderDetail,
    OrderListPage,
    OrderStatusUpdate,
    OrderUpdate,
)
from database import get_db
from models import User

router = APIRouter(tags=["orders"])


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

@router.get("/api/orders", response_model=OrderListPage)
def list_orders(
    search: Optional[str] = None,
    status_: Optional[str] = Query(None, alias="status"),
    customer_id: Optional[int] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    sort: str = Query("placed_at"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    _: User = Depends(require_permission("orders.read")),
    db: Session = Depends(get_db),
):
    """Return a filtered, sorted, paginated page of orders."""
    rows, total = service.list_orders(
        db,
        search=search,
        status=status_,
        customer_id=customer_id,
        date_from=date_from,
        date_to=date_to,
        sort=sort,
        order=order,
        page=page,
        page_size=page_size,
    )
    total_pages = math.ceil(total / page_size) if total else 0
    return OrderListPage(
        items=[service.to_list_item(o) for o in rows],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

@router.post(
    "/api/orders",
    response_model=OrderDetail,
    status_code=status.HTTP_201_CREATED,
)
def create_order(
    data: OrderCreate,
    _: User = Depends(require_permission("orders.create")),
    db: Session = Depends(get_db),
):
    """Create a new order and return its full detail view."""
    try:
        order = service.create_order(db, data)
    except (service.NotFoundError, service.BusinessRuleError, service.ConflictError) as error:
        raise _http_from_service_error(error)
    return service.to_detail(order)


# ---------------------------------------------------------------------------
# Detail
# ---------------------------------------------------------------------------

@router.get("/api/orders/{order_id}", response_model=OrderDetail)
def get_order(
    order_id: int,
    _: User = Depends(require_permission("orders.read")),
    db: Session = Depends(get_db),
):
    """Return one order, including its customer, address, and line items."""
    try:
        order = service.get_order_or_404(db, order_id)
    except service.NotFoundError as error:
        raise _http_from_service_error(error)
    return service.to_detail(order)


# ---------------------------------------------------------------------------
# Update (address / line items — pending orders only)
# ---------------------------------------------------------------------------

@router.patch("/api/orders/{order_id}", response_model=OrderDetail)
def update_order(
    order_id: int,
    data: OrderUpdate,
    _: User = Depends(require_permission("orders.update")),
    db: Session = Depends(get_db),
):
    """Edit a pending order's shipping address and/or line items."""
    try:
        order = service.update_order(db, order_id, data)
    except (service.NotFoundError, service.BusinessRuleError, service.ConflictError) as error:
        raise _http_from_service_error(error)
    return service.to_detail(order)


# ---------------------------------------------------------------------------
# Status change
# ---------------------------------------------------------------------------

@router.post("/api/orders/{order_id}/status", response_model=OrderDetail)
def change_order_status(
    order_id: int,
    data: OrderStatusUpdate,
    _: User = Depends(require_permission("orders.update")),
    db: Session = Depends(get_db),
):
    """Move an order to a new lifecycle status (or cancel it)."""
    try:
        order = service.change_status(db, order_id, data.status)
    except (service.NotFoundError, service.BusinessRuleError, service.ConflictError) as error:
        raise _http_from_service_error(error)
    return service.to_detail(order)


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------

@router.delete("/api/orders/{order_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_order(
    order_id: int,
    _: User = Depends(require_permission("orders.delete")),
    db: Session = Depends(get_db),
):
    """Delete an order (only while pending or cancelled)."""
    try:
        service.delete_order(db, order_id)
    except (service.NotFoundError, service.BusinessRuleError) as error:
        raise _http_from_service_error(error)
    return None
