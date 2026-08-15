"""
customers_schemas.py
---------------------
Pydantic "schemas" for the Customers module.

These describe the SHAPE of the data going in and out of the /api/customers
API, separately from the SQLAlchemy model in models.py. Request schemas
validate what a caller sends us; response schemas control exactly what we
send back (e.g. the owner is shown as a small summary, never the full user).
"""

import uuid
from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field

# The only statuses a customer may have. Reused by both schemas below so the
# allowed set is defined in exactly one place.
CustomerStatus = Literal["active", "inactive", "lead"]


# ---------------------------------------------------------------------------
# Small shared pieces
# ---------------------------------------------------------------------------

class OwnerSummary(BaseModel):
    """A tiny view of the owning user — enough to show a name in the UI."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    full_name: str


# ---------------------------------------------------------------------------
# Requests (data coming IN from the browser)
# ---------------------------------------------------------------------------

class CustomerCreate(BaseModel):
    """Body for POST /api/customers."""

    name: str = Field(min_length=1, max_length=255)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(default=None, max_length=50)
    company: Optional[str] = Field(default=None, max_length=255)
    status: CustomerStatus = "active"
    address_line: Optional[str] = Field(default=None, max_length=255)
    city: Optional[str] = Field(default=None, max_length=120)
    country: Optional[str] = Field(default=None, max_length=120)
    notes: Optional[str] = None
    # Defaults to the creating user when not given (see customers_service.py).
    owner_id: Optional[uuid.UUID] = None


class CustomerUpdate(BaseModel):
    """
    Body for PATCH /api/customers/{id} — a partial update.

    Every field is optional: only the fields actually sent are changed. The
    service layer relies on Pydantic's "which fields were set" tracking to
    tell "leave owner_id alone" apart from "clear owner_id" (owner_id: null).
    """

    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(default=None, max_length=50)
    company: Optional[str] = Field(default=None, max_length=255)
    status: Optional[CustomerStatus] = None
    address_line: Optional[str] = Field(default=None, max_length=255)
    city: Optional[str] = Field(default=None, max_length=120)
    country: Optional[str] = Field(default=None, max_length=120)
    notes: Optional[str] = None
    owner_id: Optional[uuid.UUID] = None


# ---------------------------------------------------------------------------
# Responses (data going OUT to the browser)
# ---------------------------------------------------------------------------

class CustomerListItem(BaseModel):
    """One row in the customers list table."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    company: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    status: CustomerStatus
    owner_id: Optional[uuid.UUID] = None
    created_at: datetime


class CustomerListPage(BaseModel):
    """A single page of customers, plus the numbers the UI needs for paging."""

    items: List[CustomerListItem]
    total: int          # total matching customers across all pages
    page: int            # the current page number (1-based)
    page_size: int        # how many rows per page
    total_pages: int      # total number of pages


class CustomerDetail(BaseModel):
    """The full view of one customer, including a summary of its owner."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    company: Optional[str] = None
    status: CustomerStatus
    address_line: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None
    notes: Optional[str] = None
    owner: Optional[OwnerSummary] = None
    created_at: datetime
    updated_at: datetime
