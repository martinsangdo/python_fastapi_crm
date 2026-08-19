"""
dashboard_schemas.py
---------------------
Pydantic "schemas" for the Dashboard module.

These describe the SHAPE of the data returned by GET /api/dashboard/stats:
small, pre-aggregated numbers the dashboard page turns into charts. Nothing
here is a database model — see models.py for the real tables this data is
computed from.
"""

from decimal import Decimal
from typing import List

from pydantic import BaseModel


class DashboardSummary(BaseModel):
    """The four headline numbers shown as cards at the top of the dashboard."""

    total_customers: int
    total_products: int
    total_orders: int
    total_revenue: Decimal


class StatusCount(BaseModel):
    """How many orders currently sit in one lifecycle status."""

    status: str
    count: int


class MonthPoint(BaseModel):
    """One point on a "per month" chart, e.g. revenue or new customers."""

    # "YYYY-MM", already in chronological order — easiest for the frontend
    # to use directly as a chart label.
    month: str
    value: Decimal


class TopProduct(BaseModel):
    """One row in the "best-selling products" chart."""

    name: str
    quantity_sold: int
    revenue: Decimal


class CategoryCount(BaseModel):
    """How many products sit in one category."""

    category: str
    count: int


class LowStockProduct(BaseModel):
    """A product whose stock is running low, worth restocking soon."""

    name: str
    stock_quantity: int


class DashboardStats(BaseModel):
    """Everything the dashboard page needs, in one response."""

    summary: DashboardSummary
    orders_by_status: List[StatusCount]
    revenue_by_month: List[MonthPoint]
    new_customers_by_month: List[MonthPoint]
    top_products: List[TopProduct]
    products_by_category: List[CategoryCount]
    low_stock_products: List[LowStockProduct]
