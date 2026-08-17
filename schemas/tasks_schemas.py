"""
tasks_schemas.py
------------------
Pydantic schemas for the PUBLIC scheduled-task endpoints (routers/tasks.py).
"""

from typing import List, Optional

from pydantic import BaseModel


class NewCustomerSummary(BaseModel):
    """One customer in the "new today" list — just enough to identify them."""

    id: int
    full_name: str
    email: str


class CustomerCareCheckResponse(BaseModel):
    """Body of POST /api/public/tasks/customer-care-check."""

    # The local date (APP_TIMEZONE) the check ran for, e.g. "2026-08-15".
    date: str
    new_customer_count: int
    new_customers: List[NewCustomerSummary]

    # Whether a Google Calendar event was JUST created this call (false when
    # there were no new customers today, or when one already existed — see
    # already_existed).
    event_created: bool
    # True when today's reminder event already existed (e.g. this endpoint
    # was called twice today) — no duplicate was created.
    already_existed: bool = False
    event_id: Optional[str] = None
    event_link: Optional[str] = None
    # When the reminder event is/was scheduled for (ISO datetime) — this is
    # EVENT_OFFSET_DAYS after `date`, not `date` itself.
    event_start: Optional[str] = None


class NewCustomersEmailCheckResponse(BaseModel):
    """Body of POST /api/public/tasks/new-customers-email-check."""

    # The local date (APP_TIMEZONE) the check ran for, e.g. "2026-08-15".
    date: str
    new_customer_count: int
    new_customers: List[NewCustomerSummary]

    # Whether a summary email was sent this call (false when there were no
    # new customers today).
    email_sent: bool
    # The Resend message id, when email_sent is True.
    email_id: Optional[str] = None
