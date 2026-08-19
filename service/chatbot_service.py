"""
chatbot_service.py
--------------------
A tiny "ask about the data" chatbot for the dashboard page.

It does NOT let the AI write or run its own SQL (that would let a cleverly
worded question trick it into destructive or overly broad queries). Instead
we hand it a JSON snapshot of the CRM's current data — customers, products,
orders, and the same aggregated numbers the dashboard charts use — and ask
it to analyze that snapshot in plain language. The AI can only see and talk
about data we chose to show it, and it can never modify anything.

Uses Groq (https://groq.com), the same AI provider already used by the RAG
experiments under tests/. Requires GROQ_API_KEY in .env.
"""

import json
import os
from typing import List

from dotenv import load_dotenv
from sqlalchemy.orm import Session

import repository.customers_repository as customers_repository
import repository.orders_repository as orders_repository
import repository.products_repository as products_repository
from schemas.chatbot_schemas import ChatMessage
from service.dashboard_service import get_dashboard_stats

load_dotenv()

GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")

# How many rows of raw data (per table) to show the AI. Keeps the prompt
# small and fast even if the database grows well past this scaffold's size —
# the dashboard summary numbers stay exact either way, only the row-level
# detail is capped.
_MAX_ROWS = 100

# How many previous turns of the conversation to replay, so follow-up
# questions work without the prompt growing without bound.
_MAX_HISTORY_TURNS = 10


class ChatbotNotConfiguredError(Exception):
    """Raised when GROQ_API_KEY is missing, so the router can return a clean error."""


def _get_client():
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ChatbotNotConfiguredError("GROQ_API_KEY is not set.")
    from groq import Groq  # imported lazily so the package is only needed if used

    return Groq(api_key=api_key)


def _data_snapshot(db: Session) -> dict:
    """A compact, JSON-safe snapshot of the CRM's data for the AI to analyze."""
    stats = get_dashboard_stats(db)
    snapshot = json.loads(stats.model_dump_json())

    customers, _ = customers_repository.list_customers(db, page_size=_MAX_ROWS)
    products, _ = products_repository.list_products(db, page_size=_MAX_ROWS)
    orders, _ = orders_repository.list_orders(db, page_size=_MAX_ROWS)

    snapshot["customers"] = [
        {
            "full_name": c.full_name,
            "email": c.email,
            "created_at": c.created_at.isoformat(),
        }
        for c in customers
    ]
    snapshot["products"] = [
        {
            "name": p.name,
            "sku": p.sku,
            "category": p.category.name if p.category else None,
            "price": str(p.price),
            "stock_quantity": p.stock_quantity,
            "is_active": p.is_active,
        }
        for p in products
    ]
    snapshot["orders"] = [
        {
            "id": o.id,
            "customer": o.customer.full_name if o.customer else None,
            "status": o.status,
            "total_amount": str(o.total_amount),
            "placed_at": o.placed_at.isoformat(),
            "item_count": len(o.items),
        }
        for o in orders
    ]
    return snapshot


def _system_prompt(snapshot: dict) -> str:
    return (
        "You are a data analysis assistant embedded in a small CRM's dashboard. "
        "Answer the user's question using ONLY the JSON data below — a snapshot "
        "of the CRM's customers, products, and orders, plus numbers already "
        "computed for the dashboard's charts. Do any sums, counts, averages, "
        "or comparisons yourself, precisely, from this data. Only the most "
        f"recent {_MAX_ROWS} rows per table are listed (use the 'summary' "
        "numbers for exact totals beyond that). If the data does not contain "
        "what's needed to answer, say so honestly instead of guessing. Keep "
        "answers concise — a few sentences or a short list. Reply in the same "
        "language the user asked in.\n\n"
        f"DATA SNAPSHOT (JSON):\n{json.dumps(snapshot, ensure_ascii=False)}"
    )


def ask(db: Session, message: str, history: List[ChatMessage]) -> str:
    """Answer one question about the CRM's data, using recent history for context."""
    client = _get_client()
    snapshot = _data_snapshot(db)

    messages = [{"role": "system", "content": _system_prompt(snapshot)}]
    for turn in history[-_MAX_HISTORY_TURNS:]:
        messages.append({"role": turn.role, "content": turn.content})
    messages.append({"role": "user", "content": message})

    response = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=messages,
        temperature=0.2,
    )
    return response.choices[0].message.content
