"""
daily_summary_schemas.py
---------------------------
Pydantic schemas for the daily sales summary email
(POST /api/public/tasks/daily-summary).
"""

from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel


class TopSellingProduct(BaseModel):
    """One row in the "best-selling today" list."""

    name: str
    quantity_sold: int
    revenue: Decimal


class DailySummaryAnalysis(BaseModel):
    """The raw numbers pulled from the database, before the AI writes them up."""

    date: str
    timezone: str

    revenue_today: Decimal
    revenue_yesterday: Decimal
    revenue_change_pct: Optional[float] = None

    orders_today: int
    orders_yesterday: int
    orders_change_pct: Optional[float] = None

    avg_order_value_today: Decimal
    avg_order_value_yesterday: Decimal

    top_products_today: List[TopSellingProduct]


class DailySummaryResult(BaseModel):
    """What POST /api/public/tasks/daily-summary returns."""

    analysis: DailySummaryAnalysis
    subject: str
    body_html: str
    recipient: str
    sent: bool
    email_id: Optional[str] = None
