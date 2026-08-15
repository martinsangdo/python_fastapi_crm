"""
customers_schemas.py
---------------------
Pydantic "schemas" for the Customers module.

These describe the SHAPE of the data going in and out of the /api/customers
API, separately from the SQLAlchemy model in models.py.
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# ---------------------------------------------------------------------------
# Small shared pieces
# ---------------------------------------------------------------------------

class AddressSummary(BaseModel):
    """One of a customer's saved shipping addresses (used by the Orders module)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    line1: str
    city: str
    postal_code: str
    country: str
    is_default: bool


# ---------------------------------------------------------------------------
# Requests (data coming IN from the browser)
# ---------------------------------------------------------------------------

class CustomerCreate(BaseModel):
    """Body for POST /api/customers."""

    email: EmailStr
    full_name: str = Field(min_length=1, max_length=255)


class CustomerUpdate(BaseModel):
    """Body for PATCH /api/customers/{id} — a partial update."""

    email: Optional[EmailStr] = None
    full_name: Optional[str] = Field(default=None, min_length=1, max_length=255)


# ---------------------------------------------------------------------------
# Responses (data going OUT to the browser)
# ---------------------------------------------------------------------------

class CustomerListItem(BaseModel):
    """One row in the customers list table."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    full_name: str
    created_at: datetime


class CustomerListPage(BaseModel):
    """A single page of customers, plus the numbers the UI needs for paging."""

    items: List[CustomerListItem]
    total: int
    page: int
    page_size: int
    total_pages: int


class CustomerDetail(BaseModel):
    """The full view of one customer."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    full_name: str
    created_at: datetime
