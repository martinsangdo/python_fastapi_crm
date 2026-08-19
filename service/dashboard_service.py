"""
dashboard_service.py
----------------------
The "business logic" layer for the Dashboard module.

Pulls raw numbers from dashboard_repository.py and shapes them into the
DashboardStats schema the frontend charts expect: monthly series filled in
with zeros for quiet months, statuses always shown in a stable order, and
money rounded to cents.
"""

from calendar import month_abbr
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, List, Sequence, Tuple

import repository.dashboard_repository as repository
from schemas.dashboard_schemas import (
    CategoryCount,
    DashboardStats,
    DashboardSummary,
    LowStockProduct,
    MonthPoint,
    StatusCount,
    TopProduct,
)
from sqlalchemy.orm import Session

# Every status an order can be in, in the order they should appear in the
# chart — regardless of how many orders (including zero) currently have it.
_STATUS_ORDER = ["pending", "paid", "shipped", "completed", "cancelled"]

# How many months of history the trend charts cover.
_TREND_MONTHS = 6

# A product at or below this stock level shows up on the "low stock" chart.
_LOW_STOCK_THRESHOLD = 10


def _last_n_months(n: int) -> List[Tuple[int, int]]:
    """Return the last `n` (year, month) pairs, oldest first, ending this month."""
    now = datetime.now(timezone.utc)
    months = []
    year, month = now.year, now.month
    for _ in range(n):
        months.append((year, month))
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    months.reverse()
    return months


def _month_label(year: int, month: int) -> str:
    """e.g. (2026, 3) -> 'Mar 2026' — short and readable on a chart axis."""
    return f"{month_abbr[month]} {year}"


def _bucket_by_month(
    timestamps_with_values: Sequence[Tuple[datetime, Decimal]],
) -> Dict[Tuple[int, int], Decimal]:
    """Sum values into (year, month) buckets."""
    buckets: Dict[Tuple[int, int], Decimal] = defaultdict(lambda: Decimal(0))
    for ts, value in timestamps_with_values:
        buckets[(ts.year, ts.month)] += value
    return buckets


def _monthly_series(
    timestamps_with_values: Sequence[Tuple[datetime, Decimal]],
) -> List[MonthPoint]:
    """Turn raw (timestamp, value) pairs into a zero-filled, ordered series."""
    buckets = _bucket_by_month(timestamps_with_values)
    months = _last_n_months(_TREND_MONTHS)
    return [
        MonthPoint(month=_month_label(year, month), value=buckets.get((year, month), Decimal(0)))
        for year, month in months
    ]


def get_dashboard_stats(db: Session) -> DashboardStats:
    """Compute every number the dashboard page needs, in one call."""

    summary = DashboardSummary(
        total_customers=repository.count_customers(db),
        total_products=repository.count_products(db),
        total_orders=repository.count_orders(db),
        total_revenue=repository.total_revenue(db),
    )

    status_counts = dict(repository.orders_by_status(db))
    orders_by_status = [
        StatusCount(status=status, count=status_counts.get(status, 0))
        for status in _STATUS_ORDER
    ]

    since = datetime.now(timezone.utc) - timedelta(days=31 * (_TREND_MONTHS - 1) + 15)

    revenue_rows = [(ts, Decimal(amount)) for ts, amount in repository.orders_since(db, since)]
    revenue_by_month = _monthly_series(revenue_rows)

    customer_rows = [(ts, Decimal(1)) for ts in repository.customers_since(db, since)]
    new_customers_by_month = _monthly_series(customer_rows)

    top_products = [
        TopProduct(name=name, quantity_sold=qty, revenue=revenue)
        for name, qty, revenue in repository.top_products_by_revenue(db, limit=5)
    ]

    products_by_category = [
        CategoryCount(category=name, count=count)
        for name, count in repository.products_by_category(db)
    ]

    low_stock_products = [
        LowStockProduct(name=name, stock_quantity=qty)
        for name, qty in repository.low_stock_products(
            db, threshold=_LOW_STOCK_THRESHOLD, limit=5
        )
    ]

    return DashboardStats(
        summary=summary,
        orders_by_status=orders_by_status,
        revenue_by_month=revenue_by_month,
        new_customers_by_month=new_customers_by_month,
        top_products=top_products,
        products_by_category=products_by_category,
        low_stock_products=low_stock_products,
    )
