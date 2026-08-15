"""
routers/products.py
--------------------
The HTTP layer of the Products module: every /api/products endpoint.

Like routers/customers.py, this file stays thin. Each route:
  1. Receives validated input (thanks to the Pydantic schemas).
  2. Is guarded by `require_permission(...)` so only allowed roles get in.
  3. Calls a function in products_service.py to do the real work.
  4. Turns any typed service error into the matching HTTP status code.

Endpoints:
    GET    /api/products                  -> list (paged/filtered/sorted)
    POST   /api/products                  -> create
    GET    /api/products/{id}             -> detail (with category summary)
    PATCH  /api/products/{id}             -> partial update
    DELETE /api/products/{id}             -> hard delete (blocked if on any order)
    POST   /api/products/{id}/activate    -> convenience toggle -> is_active=True
    POST   /api/products/{id}/deactivate  -> convenience toggle -> is_active=False
"""

import math
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

import service.products_service as service
from authorization import require_permission
from schemas.products_schemas import (
    ProductCreate,
    ProductDetail,
    ProductListItem,
    ProductListPage,
    ProductUpdate,
)
from database import get_db
from models import User

router = APIRouter(tags=["products"])


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

@router.get("/api/products", response_model=ProductListPage)
def list_products(
    search: Optional[str] = None,
    category_id: Optional[int] = None,
    is_active: Optional[bool] = None,
    in_stock: Optional[bool] = None,
    min_price: Optional[Decimal] = None,
    max_price: Optional[Decimal] = None,
    sort: str = Query("created_at"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    _: User = Depends(require_permission("products.read")),
    db: Session = Depends(get_db),
):
    """Return a filtered, sorted, paginated page of products."""
    rows, total = service.list_products(
        db,
        search=search,
        category_id=category_id,
        is_active=is_active,
        in_stock=in_stock,
        min_price=min_price,
        max_price=max_price,
        sort=sort,
        order=order,
        page=page,
        page_size=page_size,
    )
    total_pages = math.ceil(total / page_size) if total else 0
    return ProductListPage(
        items=[ProductListItem.model_validate(p) for p in rows],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

@router.post(
    "/api/products",
    response_model=ProductDetail,
    status_code=status.HTTP_201_CREATED,
)
def create_product(
    data: ProductCreate,
    _: User = Depends(require_permission("products.create")),
    db: Session = Depends(get_db),
):
    """Create a new product and return its full detail view."""
    try:
        product = service.create_product(db, data)
    except (service.NotFoundError, service.BusinessRuleError, service.ConflictError) as error:
        raise _http_from_service_error(error)
    return service.to_detail(product)


# ---------------------------------------------------------------------------
# Detail
# ---------------------------------------------------------------------------

@router.get("/api/products/{product_id}", response_model=ProductDetail)
def get_product(
    product_id: int,
    _: User = Depends(require_permission("products.read")),
    db: Session = Depends(get_db),
):
    """Return one product, including a summary of its category."""
    try:
        product = service.get_product_or_404(db, product_id)
    except service.NotFoundError as error:
        raise _http_from_service_error(error)
    return service.to_detail(product)


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------

@router.patch("/api/products/{product_id}", response_model=ProductDetail)
def update_product(
    product_id: int,
    data: ProductUpdate,
    _: User = Depends(require_permission("products.update")),
    db: Session = Depends(get_db),
):
    """Apply a partial update to a product."""
    try:
        product = service.update_product(db, product_id, data)
    except (service.NotFoundError, service.BusinessRuleError, service.ConflictError) as error:
        raise _http_from_service_error(error)
    return service.to_detail(product)


# ---------------------------------------------------------------------------
# Activate / deactivate
# ---------------------------------------------------------------------------

@router.post("/api/products/{product_id}/activate", response_model=ProductDetail)
def activate_product(
    product_id: int,
    _: User = Depends(require_permission("products.update")),
    db: Session = Depends(get_db),
):
    """Mark a product active again — visible to new-order product pickers."""
    try:
        product = service.set_active(db, product_id, True)
    except service.NotFoundError as error:
        raise _http_from_service_error(error)
    return service.to_detail(product)


@router.post("/api/products/{product_id}/deactivate", response_model=ProductDetail)
def deactivate_product(
    product_id: int,
    _: User = Depends(require_permission("products.update")),
    db: Session = Depends(get_db),
):
    """Mark a product inactive — hidden from new orders, kept in history."""
    try:
        product = service.set_active(db, product_id, False)
    except service.NotFoundError as error:
        raise _http_from_service_error(error)
    return service.to_detail(product)


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------

@router.delete("/api/products/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product(
    product_id: int,
    _: User = Depends(require_permission("products.delete")),
    db: Session = Depends(get_db),
):
    """Permanently delete a product (blocked if it appears on any order)."""
    try:
        service.delete_product(db, product_id)
    except (service.NotFoundError, service.ConflictError) as error:
        raise _http_from_service_error(error)
    return None
