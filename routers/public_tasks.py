"""
routers/public_tasks.py
--------------------------
PUBLIC endpoints (no user login) meant to be called by an external scheduler
— e.g. a daily cron job — rather than a browser. See public_auth.py: every
route here requires the shared secret "X-API-Key" header (PUBLIC_TASK_API_KEY
in .env).

Endpoints:
    POST /api/public/tasks/daily-summary -> analyze today's sales and email
                                             the director a summary
                                             (Groq writes it, Resend sends it)
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

import service.daily_summary_service as daily_summary_service
from database import get_db
from public_auth import require_public_api_key
from schemas.daily_summary_schemas import DailySummaryResult
from service.groq_client import GroqNotConfiguredError
from service.resend_client import EmailNotConfiguredError

router = APIRouter(tags=["public"], dependencies=[Depends(require_public_api_key)])


@router.post("/api/public/tasks/daily-summary", response_model=DailySummaryResult)
def send_daily_summary(
    dry_run: bool = False,
    db: Session = Depends(get_db),
):
    """
    Analyze today's revenue/orders/best-sellers vs. yesterday, have Groq
    write it up in Vietnamese, and email it to the director via Resend.

    Pass ?dry_run=true to run the whole pipeline (including the Groq call)
    WITHOUT actually sending the email — handy for testing.
    """
    try:
        return daily_summary_service.send_daily_summary(db, dry_run=dry_run)
    except daily_summary_service.DailySummaryNotConfiguredError as error:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error))
    except GroqNotConfiguredError:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The AI is not configured (missing GROQ_API_KEY).",
        )
    except EmailNotConfiguredError:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Email sending is not configured (missing RESEND_API_KEY).",
        )
