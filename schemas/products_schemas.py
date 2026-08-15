"""
products_schemas.py
--------------------
Pydantic "schemas" for the Products module.

These describe the SHAPE of the data going in and out of the /api/products
API, separately from the SQLAlchemy model in models.py.
"""

from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Small shared pieces
# ---------------------------------------------------------------------------

class CategorySummary(BaseModel):
    """A tiny view of the owning category — enough to show a name in the UI."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str


# ---------------------------------------------------------------------------
# Requests (data coming IN from the browser)
# ---------------------------------------------------------------------------

class ProductCreate(BaseModel):
    """Body for POST /api/products."""

    category_id: int
    sku: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    description: Optional[str] = None
    price: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    stock_quantity: int = Field(default=0, ge=0)
    is_active: bool = True


class ProductUpdate(BaseModel):
    """Body for PATCH /api/products/{id} — a partial update."""

    category_id: Optional[int] = None
    sku: Optional[str] = Field(default=None, min_length=1, max_length=64)
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = None
    price: Optional[Decimal] = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    stock_quantity: Optional[int] = Field(default=None, ge=0)
    is_active: Optional[bool] = None


# ---------------------------------------------------------------------------
# Responses (data going OUT to the browser)
# ---------------------------------------------------------------------------

class ProductListItem(BaseModel):
    """One row in the products list table."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    sku: str
    name: str
    category_id: int
    price: Decimal
    stock_quantity: int
    is_active: bool


class ProductListPage(BaseModel):
    """A single page of products, plus the numbers the UI needs for paging."""

    items: List[ProductListItem]
    total: int
    page: int
    page_size: int
    total_pages: int


class ProductDetail(BaseModel):
    """The full view of one product, including a summary of its category."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    sku: str
    name: str
    description: Optional[str] = None
    price: Decimal
    stock_quantity: int
    is_active: bool
    category: CategorySummary
    created_at: datetime
