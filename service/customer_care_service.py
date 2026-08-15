"""
customer_care_service.py
--------------------------
Business logic behind the "new customers today -> Google Calendar reminder"
public task (see routers/tasks.py).

Flow, once a day (triggered by an external scheduler hitting the public
endpoint):
  1. Find every customer whose `created_at` falls within "today", in
     APP_TIMEZONE.
  2. If there are none, do nothing — return a summary saying so.
  3. If there are some, look for an event ALREADY created for today (marked
     with a private extended property — see _EVENT_MARKER_KEY below). If one
     exists, do not create another — this makes the endpoint safe to call
     more than once in a day (a scheduler retry, someone testing by hand,
     ...) without spamming duplicate events.
  4. Otherwise, create ONE Google Calendar event listing the new customers,
     so the sales team gets a reminder to reach out and follow up.

This file knows nothing about HTTP; it just returns a plain dict that the
router turns directly into the JSON response.
"""

import os
from datetime import datetime, time, timedelta
from typing import List
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from sqlalchemy.orm import Session

import repository.customers_repository as customers_repo
import service.google_calendar_service as calendar_service
from models import Customer

load_dotenv()

# The timezone "today" is measured in — a customer who signs up at 23:30
# local time should count as "today", not tomorrow in UTC.
APP_TIMEZONE = os.getenv("APP_TIMEZONE", "Asia/Ho_Chi_Minh")

# The reminder event is scheduled this many days AFTER today (a follow-up
# check-in, not a same-day one), at the given time of day, running for the
# given duration.
EVENT_OFFSET_DAYS = int(os.getenv("CUSTOMER_CARE_EVENT_OFFSET_DAYS", "7"))
EVENT_HOUR = int(os.getenv("CUSTOMER_CARE_EVENT_HOUR", "15"))
EVENT_MINUTE = int(os.getenv("CUSTOMER_CARE_EVENT_MINUTE", "0"))
EVENT_DURATION_MINUTES = int(os.getenv("CUSTOMER_CARE_EVENT_DURATION_MINUTES", "30"))

# Marks an event as "the customer-care reminder for [date]" so a later call
# (e.g. a scheduler retry) can find it and skip creating a duplicate.
_EVENT_MARKER_KEY = "fastapi_crm_customer_care_check_date"


def _today_bounds(tz: ZoneInfo) -> tuple[datetime, datetime]:
    """The [start, end) of "today" in `tz`, as timezone-aware datetimes."""
    now_local = datetime.now(tz)
    start_local = datetime.combine(now_local.date(), time.min, tzinfo=tz)
    end_local = start_local + timedelta(days=1)
    return start_local, end_local


def _format_customer_list(customers: List[Customer]) -> str:
    """One "- Name (email)" line per customer, for the event description."""
    return "\n".join(f"- {c.full_name} ({c.email})" for c in customers)


def check_new_customers_and_notify(db: Session) -> dict:
    """
    Run the check once. Returns a plain dict summarizing what happened,
    used directly as the API response (see schemas/tasks_schemas.py).
    """
    tz = ZoneInfo(APP_TIMEZONE)
    start_local, end_local = _today_bounds(tz)
    date_str = start_local.date().isoformat()

    new_customers = customers_repo.list_created_between(db, start_local, end_local)

    result = {
        "date": date_str,
        "new_customer_count": len(new_customers),
        "new_customers": [
            {"id": c.id, "full_name": c.full_name, "email": c.email}
            for c in new_customers
        ],
        "event_created": False,
        "already_existed": False,
        "event_id": None,
        "event_link": None,
        "event_start": None,
    }

    if not new_customers:
        return result

    # The reminder is scheduled a few days OUT from today, not today itself.
    reminder_day = start_local + timedelta(days=EVENT_OFFSET_DAYS)
    event_start = reminder_day.replace(
        hour=EVENT_HOUR, minute=EVENT_MINUTE, second=0, microsecond=0
    )
    event_end = event_start + timedelta(minutes=EVENT_DURATION_MINUTES)
    result["event_start"] = event_start.isoformat()

    # Don't create a second event if this "today" has already been handled
    # (e.g. the scheduler retried, or someone called the endpoint twice).
    # The lookup window must cover the REMINDER day (event_start's date),
    # not today — Google filters events by when they occur, and the event
    # is scheduled EVENT_OFFSET_DAYS in the future, not today.
    reminder_day_start = datetime.combine(event_start.date(), time.min, tzinfo=tz)
    reminder_day_end = reminder_day_start + timedelta(days=1)
    existing = calendar_service.find_event_by_private_property(
        key=_EVENT_MARKER_KEY,
        value=date_str,
        time_min=reminder_day_start,
        time_max=reminder_day_end,
    )
    if existing is not None:
        result["already_existed"] = True
        result["event_id"] = existing.get("id")
        result["event_link"] = existing.get("htmlLink")
        return result

    summary = f"Chăm sóc khách hàng mới - {start_local.strftime('%d/%m/%Y')}"
    description = (
        f"Có {len(new_customers)} khách hàng mới đăng ký ngày {start_local.strftime('%d/%m/%Y')}, "
        f"cần liên hệ chăm sóc:\n\n{_format_customer_list(new_customers)}"
    )

    event = calendar_service.create_event(
        summary=summary,
        description=description,
        start=event_start,
        end=event_end,
        timezone=APP_TIMEZONE,
        extended_properties={_EVENT_MARKER_KEY: date_str},
    )

    result["event_created"] = True
    result["event_id"] = event.get("id")
    result["event_link"] = event.get("htmlLink")
    return result
