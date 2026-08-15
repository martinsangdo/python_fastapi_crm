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
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

import service.customer_care_service as customer_care_service
from database import get_db
from public_auth import require_public_api_key
from schemas.tasks_schemas import CustomerCareCheckResponse
from service.google_calendar_service import CalendarConfigError

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
