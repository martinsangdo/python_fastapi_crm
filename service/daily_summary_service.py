"""
daily_summary_service.py
---------------------------
Builds and sends the daily sales summary email for the director.

Three steps, kept in three small functions:
  1. build_analysis()  — pull today's/yesterday's numbers straight from the
                          database (no AI involved — these figures are exact).
  2. _compose_email()  — ask Groq to turn that JSON into a short, readable
                          Vietnamese email (subject + HTML body).
  3. send_daily_summary() — orchestrates the two above, then sends the email
                          through Resend (unless dry_run is requested).
"""

import json
import os
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from sqlalchemy.orm import Session

import repository.daily_summary_repository as repository
import service.resend_client as resend_client
from schemas.daily_summary_schemas import DailySummaryAnalysis, DailySummaryResult, TopSellingProduct
from service.groq_client import GROQ_MODEL, get_client

load_dotenv()

# How many best-selling products to list in the email.
_TOP_PRODUCTS_LIMIT = 3


class DailySummaryNotConfiguredError(Exception):
    """Raised when DAILY_SUMMARY_EMAIL is missing, so the router can return a clean error."""


def _today_range(tz_name: str):
    """The [start, end) of "today" in the given timezone, as tz-aware datetimes."""
    tz = ZoneInfo(tz_name)
    now_local = datetime.now(tz)
    start = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    return start, end


def _pct_change(current: Decimal, previous: Decimal) -> Optional[float]:
    """% change from `previous` to `current`, or None if there's nothing to compare against."""
    if previous == 0:
        return None
    return float((current - previous) / previous * 100)


def build_analysis(db: Session) -> DailySummaryAnalysis:
    """Compute today-vs-yesterday sales numbers directly from the database."""
    tz_name = os.getenv("APP_TIMEZONE", "UTC")
    today_start, today_end = _today_range(tz_name)
    yesterday_start = today_start - timedelta(days=1)

    revenue_today, orders_today = repository.sales_between(db, today_start, today_end)
    revenue_yesterday, orders_yesterday = repository.sales_between(db, yesterday_start, today_start)

    top_products = repository.top_selling_products_between(
        db, today_start, today_end, limit=_TOP_PRODUCTS_LIMIT
    )

    return DailySummaryAnalysis(
        date=today_start.date().isoformat(),
        timezone=tz_name,
        revenue_today=revenue_today,
        revenue_yesterday=revenue_yesterday,
        revenue_change_pct=_pct_change(revenue_today, revenue_yesterday),
        orders_today=orders_today,
        orders_yesterday=orders_yesterday,
        orders_change_pct=_pct_change(Decimal(orders_today), Decimal(orders_yesterday)),
        avg_order_value_today=(revenue_today / orders_today) if orders_today else Decimal(0),
        avg_order_value_yesterday=(revenue_yesterday / orders_yesterday) if orders_yesterday else Decimal(0),
        top_products_today=[
            TopSellingProduct(name=name, quantity_sold=qty, revenue=revenue)
            for name, qty, revenue in top_products
        ],
    )


def _compose_email(analysis: DailySummaryAnalysis) -> dict:
    """Ask Groq to turn the analysis into a short Vietnamese email (subject + HTML body)."""
    client = get_client()
    data = json.loads(analysis.model_dump_json())

    system_prompt = (
        "Bạn là trợ lý viết báo cáo kinh doanh hằng ngày gửi cho giám đốc một "
        "cửa hàng nhỏ. Dựa CHÍNH XÁC vào dữ liệu JSON dưới đây — không bịa "
        "thêm số liệu nào ngoài dữ liệu được cung cấp. Viết một email ngắn "
        "gọn, chuyên nghiệp, bằng tiếng Việt, gồm: doanh thu hôm nay và số "
        "đơn hàng hôm nay, so sánh tăng/giảm (%) so với hôm qua, danh sách "
        "sản phẩm bán chạy nhất hôm nay, và 1-2 câu nhận xét ngắn dựa trên "
        "xu hướng tăng/giảm đó. Nếu hôm nay chưa có đơn hàng nào, hãy nói rõ "
        "điều đó thay vì suy diễn.\n\n"
        "Trả lời DUY NHẤT một object JSON hợp lệ, đúng cấu trúc sau, không "
        "kèm giải thích gì thêm:\n"
        '{"subject": "...", "body_html": "..."}\n'
        "body_html là nội dung email dạng HTML đơn giản (dùng các thẻ <p>, "
        "<ul>, <li>, <strong>), KHÔNG bọc trong <html>/<body>.\n\n"
        f"DỮ LIỆU (JSON):\n{json.dumps(data, ensure_ascii=False)}"
    )

    response = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[{"role": "system", "content": system_prompt}],
        temperature=0.3,
        response_format={"type": "json_object"},
    )
    parsed = json.loads(response.choices[0].message.content)

    return {
        "subject": parsed.get("subject") or f"Báo cáo kinh doanh ngày {analysis.date}",
        "body_html": parsed.get("body_html") or "<p>Không có nội dung.</p>",
    }


def send_daily_summary(db: Session, *, dry_run: bool = False) -> DailySummaryResult:
    """
    Analyze today's sales, have Groq write it up, and email it to the
    director via Resend. With dry_run=True, everything runs except the
    actual send — useful for testing the pipeline without emailing anyone.
    """
    recipient = os.getenv("DAILY_SUMMARY_EMAIL")
    if not recipient:
        raise DailySummaryNotConfiguredError("DAILY_SUMMARY_EMAIL is not set.")

    analysis = build_analysis(db)
    email = _compose_email(analysis)

    email_id = None
    if not dry_run:
        email_id = resend_client.send_email(
            to=recipient, subject=email["subject"], html=email["body_html"]
        )

    return DailySummaryResult(
        analysis=analysis,
        subject=email["subject"],
        body_html=email["body_html"],
        recipient=recipient,
        sent=not dry_run,
        email_id=email_id,
    )
