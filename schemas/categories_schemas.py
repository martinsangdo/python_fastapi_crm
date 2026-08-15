"""
categories_schemas.py
----------------------
Pydantic "schemas" for the Categories module.

These describe the SHAPE of the data going in and out of the /api/categories
API, separately from the SQLAlchemy model in models.py.
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Requests (data coming IN from the browser)
# ---------------------------------------------------------------------------

class CategoryCreate(BaseModel):
    """Body for POST /api/categories."""

    name: str = Field(min_length=1, max_length=255)
    # Optional — generated from `name` in the service layer when omitted
    # (e.g. "Home & Kitchen" -> "home-kitchen").
    slug: Optional[str] = Field(default=None, max_length=255)


class CategoryUpdate(BaseModel):
    """Body for PATCH /api/categories/{id} — a partial update."""

    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    slug: Optional[str] = Field(default=None, max_length=255)


# ---------------------------------------------------------------------------
# Responses (data going OUT to the browser)
# ---------------------------------------------------------------------------

class CategoryListItem(BaseModel):
    """One row in the categories list table."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str
    created_at: datetime


class CategoryListPage(BaseModel):
    """A single page of categories, plus the numbers the UI needs for paging."""

    items: List[CategoryListItem]
    total: int
    page: int
    page_size: int
    total_pages: int


class CategoryDetail(BaseModel):
    """The full view of one category, including how many products use it."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str
    product_count: int
    created_at: datetime
