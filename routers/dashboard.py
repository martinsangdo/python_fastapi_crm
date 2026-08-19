"""
routers/dashboard.py
---------------------
The HTTP layer of the Dashboard module: a single read-only endpoint that
feeds the charts on the /dashboard page.

Endpoints:
    GET /api/dashboard/stats -> summary numbers + chart-ready series
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

import service.dashboard_service as service
from authorization import require_permission
from database import get_db
from models import User
from schemas.dashboard_schemas import DashboardStats

router = APIRouter(tags=["dashboard"])


@router.get("/api/dashboard/stats", response_model=DashboardStats)
def get_dashboard_stats(
    _: User = Depends(require_permission("dashboard.view")),
    db: Session = Depends(get_db),
):
    """Return the aggregated numbers the dashboard page renders as charts."""
    return service.get_dashboard_stats(db)
