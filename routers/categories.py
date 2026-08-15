"""
routers/categories.py
----------------------
The HTTP layer of the Categories module: every /api/categories endpoint.

Like routers/customers.py, this file stays thin. Each route:
  1. Receives validated input (thanks to the Pydantic schemas).
  2. Is guarded by `require_permission(...)` so only allowed roles get in.
  3. Calls a function in categories_service.py to do the real work.
  4. Turns any typed service error into the matching HTTP status code.

Endpoints:
    GET    /api/categories        -> list (paged/filtered/sorted)
    POST   /api/categories        -> create
    GET    /api/categories/{id}   -> detail (with product count)
    PATCH  /api/categories/{id}   -> partial update
    DELETE /api/categories/{id}   -> hard delete (blocked if products use it)
"""

import math
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

import service.categories_service as service
from authorization import require_permission
from schemas.categories_schemas import (
    CategoryCreate,
    CategoryDetail,
    CategoryListItem,
    CategoryListPage,
    CategoryUpdate,
)
from database import get_db
from models import User

router = APIRouter(tags=["categories"])


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

@router.get("/api/categories", response_model=CategoryListPage)
def list_categories(
    search: Optional[str] = None,
    sort: str = Query("created_at"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    _: User = Depends(require_permission("categories.read")),
    db: Session = Depends(get_db),
):
    """Return a filtered, sorted, paginated page of categories."""
    rows, total = service.list_categories(
        db, search=search, sort=sort, order=order, page=page, page_size=page_size
    )
    total_pages = math.ceil(total / page_size) if total else 0
    return CategoryListPage(
        items=[CategoryListItem.model_validate(c) for c in rows],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

@router.post(
    "/api/categories",
    response_model=CategoryDetail,
    status_code=status.HTTP_201_CREATED,
)
def create_category(
    data: CategoryCreate,
    _: User = Depends(require_permission("categories.create")),
    db: Session = Depends(get_db),
):
    """Create a new category and return its full detail view."""
    try:
        category = service.create_category(db, data)
    except (service.BusinessRuleError, service.ConflictError) as error:
        raise _http_from_service_error(error)
    return service.to_detail(db, category)


# ---------------------------------------------------------------------------
# Detail
# ---------------------------------------------------------------------------

@router.get("/api/categories/{category_id}", response_model=CategoryDetail)
def get_category(
    category_id: int,
    _: User = Depends(require_permission("categories.read")),
    db: Session = Depends(get_db),
):
    """Return one category, including how many products use it."""
    try:
        category = service.get_category_or_404(db, category_id)
    except service.NotFoundError as error:
        raise _http_from_service_error(error)
    return service.to_detail(db, category)


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------

@router.patch("/api/categories/{category_id}", response_model=CategoryDetail)
def update_category(
    category_id: int,
    data: CategoryUpdate,
    _: User = Depends(require_permission("categories.update")),
    db: Session = Depends(get_db),
):
    """Apply a partial update to a category."""
    try:
        category = service.update_category(db, category_id, data)
    except (service.NotFoundError, service.BusinessRuleError, service.ConflictError) as error:
        raise _http_from_service_error(error)
    return service.to_detail(db, category)


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------

@router.delete("/api/categories/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_category(
    category_id: int,
    _: User = Depends(require_permission("categories.delete")),
    db: Session = Depends(get_db),
):
    """Permanently delete a category (blocked if any product still uses it)."""
    try:
        service.delete_category(db, category_id)
    except (service.NotFoundError, service.ConflictError) as error:
        raise _http_from_service_error(error)
    return None
