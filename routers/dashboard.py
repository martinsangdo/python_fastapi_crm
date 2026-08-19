"""
routers/dashboard.py
---------------------
The HTTP layer of the Dashboard module.

Endpoints:
    GET  /api/dashboard/stats -> summary numbers + chart-ready series
    POST /api/dashboard/chat  -> ask the AI a question about the CRM's data
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

import service.chatbot_service as chatbot_service
import service.dashboard_service as service
from authorization import require_permission
from database import get_db
from models import User
from schemas.chatbot_schemas import ChatRequest, ChatResponse
from schemas.dashboard_schemas import DashboardStats

router = APIRouter(tags=["dashboard"])


@router.get("/api/dashboard/stats", response_model=DashboardStats)
def get_dashboard_stats(
    _: User = Depends(require_permission("dashboard.view")),
    db: Session = Depends(get_db),
):
    """Return the aggregated numbers the dashboard page renders as charts."""
    return service.get_dashboard_stats(db)


@router.post("/api/dashboard/chat", response_model=ChatResponse)
def chat_about_dashboard_data(
    data: ChatRequest,
    _: User = Depends(require_permission("dashboard.view")),
    db: Session = Depends(get_db),
):
    """Answer a natural-language question about the CRM's data."""
    try:
        reply = chatbot_service.ask(db, data.message, data.history)
    except chatbot_service.ChatbotNotConfiguredError:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The chatbot is not configured (missing GROQ_API_KEY).",
        )
    return ChatResponse(reply=reply)
