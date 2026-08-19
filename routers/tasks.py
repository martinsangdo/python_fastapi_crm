"""
routers/tasks.py
------------------
PUBLIC scheduled-task endpoints — meant to be triggered by an external
scheduler (a cron job, Google Cloud Scheduler, cron-job.org, ...) rather
than a logged-in browser user. These do NOT use the JWT/RBAC system; instead
they check a shared secret via require_public_api_key (see public_auth.py).

Endpoints:
    POST /api/public/tasks/customer-care-check
        -> check for customers created today; if there are any, create ONE
           Google Calendar follow-up event (EVENT_OFFSET_DAYS out) listing
           them. Safe to call more than once a day — a second call for the
           same day finds the existing event instead of duplicating it.
    POST /api/public/tasks/new-customers-email-check
        -> check for customers created today; if there are any, email ONE
           summary to CUSTOMER_CARE_NOTIFY_EMAIL via Resend. Meant to be
           called once a day — there is no dedupe, so a second call the
           same day sends a second email.
    POST /api/public/tasks/latest-customer-ntfy-notify
        -> look up the single most recently created customer and push ONE
           ntfy (https://ntfy.sh) mobile-app notification naming them. No
           "today" filtering and no dedupe — safe to call any time.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

import service.customer_care_service as customer_care_service
from database import get_db
from public_auth import require_public_api_key
from schemas.tasks_schemas import (
    CustomerCareCheckResponse,
    LatestCustomerNtfyNotifyResponse,
    NewCustomersEmailCheckResponse,
)
from service.email_service import EmailConfigError
from service.google_calendar_service import CalendarConfigError
from service.ntfy_service import NtfyConfigError

router = APIRouter(tags=["tasks"])


@router.post(
    "/api/public/tasks/customer-care-check",
    response_model=CustomerCareCheckResponse,
    dependencies=[Depends(require_public_api_key)],
)
def customer_care_check(db: Session = Depends(get_db)):
    """
    Check for customers created today (table `customers`); if there are
    any, create ONE Google Calendar follow-up event listing them so the
    sales team knows to reach out (duplicate calls for the same day are
    detected and skipped, not re-created).

    Call this once a day from an external scheduler:
        POST /api/public/tasks/customer-care-check
        X-API-Key: <PUBLIC_TASK_API_KEY>
    """
    try:
        return customer_care_service.check_new_customers_and_notify(db)
    except CalendarConfigError as error:
        # A config problem (missing key file / calendar id), not a bad
        # request — 503 tells the caller "try again once this is fixed".
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error))


@router.post(
    "/api/public/tasks/new-customers-email-check",
    response_model=NewCustomersEmailCheckResponse,
    dependencies=[Depends(require_public_api_key)],
)
def new_customers_email_check(db: Session = Depends(get_db)):
    """
    Check for customers created today (table `customers`); if there are
    any, email ONE summary to CUSTOMER_CARE_NOTIFY_EMAIL via Resend.

    Call this once a day from an external scheduler:
        POST /api/public/tasks/new-customers-email-check
        X-API-Key: <PUBLIC_TASK_API_KEY>
    """
    try:
        return customer_care_service.check_new_customers_and_email(db)
    except EmailConfigError as error:
        # A config problem (missing API key / recipient) or a Resend
        # rejection — 503 tells the caller "try again once this is fixed".
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error))


@router.post(
    "/api/public/tasks/latest-customer-ntfy-notify",
    response_model=LatestCustomerNtfyNotifyResponse,
    dependencies=[Depends(require_public_api_key)],
)
def latest_customer_ntfy_notify(db: Session = Depends(get_db)):
    """
    Push ONE ntfy (https://ntfy.sh) push notification naming the single most
    recently created customer. Subscribe to NTFY_TOPIC in the ntfy mobile
    app to receive it.

    Call this whenever you want a fresh check (e.g. from an external
    scheduler, or by hand):
        POST /api/public/tasks/latest-customer-ntfy-notify
        X-API-Key: <PUBLIC_TASK_API_KEY>
    """
    try:
        return customer_care_service.notify_latest_customer_via_ntfy(db)
    except NtfyConfigError as error:
        # A config problem (missing topic) or ntfy rejecting the request —
        # 503 tells the caller "try again once this is fixed".
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error))
