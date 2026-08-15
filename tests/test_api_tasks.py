"""
tests/test_api_tasks.py
-------------------------
Tests for the PUBLIC scheduled-task endpoint (routers/tasks.py). Unlike the
rest of the API, this endpoint is gated by a shared X-API-Key header instead
of a JWT bearer token — see public_auth.py — so these tests don't use the
conftest `seed`/`crud_seed` fixtures (no login involved).

The real Google Calendar API is never called: service.customer_care_service
calls `calendar_service.find_event_by_private_property(...)` and
`calendar_service.create_event(...)`, both monkeypatched per test.
"""

from conftest import TEST_PUBLIC_API_KEY

import service.customer_care_service as customer_care_service
from models import Customer
from service.google_calendar_service import CalendarConfigError

ENDPOINT = "/api/public/tasks/customer-care-check"


def _create_customer(db_session, email, full_name):
    customer = Customer(email=email, full_name=full_name)
    db_session.add(customer)
    db_session.commit()
    return customer


def _stub_no_existing_event(monkeypatch):
    """By default, pretend no reminder event exists yet for today."""
    monkeypatch.setattr(
        customer_care_service.calendar_service,
        "find_event_by_private_property",
        lambda **kwargs: None,
    )


# ---------------------------------------------------------------------------
# Authentication (X-API-Key, not JWT)
# ---------------------------------------------------------------------------

def test_missing_api_key_is_unauthorized(client):
    response = client.post(ENDPOINT)
    assert response.status_code == 401


def test_wrong_api_key_is_unauthorized(client):
    response = client.post(ENDPOINT, headers={"X-API-Key": "not-the-real-key"})
    assert response.status_code == 401


def test_unconfigured_api_key_fails_closed(client, monkeypatch):
    """If the operator hasn't set PUBLIC_TASK_API_KEY, every call is refused."""
    import public_auth

    monkeypatch.setattr(public_auth, "PUBLIC_TASK_API_KEY", None)
    response = client.post(ENDPOINT, headers={"X-API-Key": "anything"})
    assert response.status_code == 503


# ---------------------------------------------------------------------------
# No new customers today -> no calendar call at all
# ---------------------------------------------------------------------------

def test_no_new_customers_skips_calendar_call(client, db_session, monkeypatch):
    calls = []
    monkeypatch.setattr(
        customer_care_service.calendar_service,
        "create_event",
        lambda **kwargs: calls.append(kwargs),
    )

    response = client.post(ENDPOINT, headers={"X-API-Key": TEST_PUBLIC_API_KEY})
    assert response.status_code == 200
    body = response.json()
    assert body["event_created"] is False
    assert body["already_existed"] is False
    assert body["new_customer_count"] == 0
    assert body["new_customers"] == []
    assert calls == []  # the Calendar API was never called


# ---------------------------------------------------------------------------
# New customers today -> one calendar event listing them, scheduled out
# ---------------------------------------------------------------------------

def test_new_customers_creates_one_calendar_event(client, db_session, monkeypatch):
    _create_customer(db_session, "new1@example.com", "New Customer One")
    _create_customer(db_session, "new2@example.com", "New Customer Two")
    _stub_no_existing_event(monkeypatch)

    calls = []

    def fake_create_event(**kwargs):
        calls.append(kwargs)
        return {"id": "evt123", "htmlLink": "https://calendar.google.com/event?eid=evt123"}

    monkeypatch.setattr(customer_care_service.calendar_service, "create_event", fake_create_event)

    response = client.post(ENDPOINT, headers={"X-API-Key": TEST_PUBLIC_API_KEY})
    assert response.status_code == 200
    body = response.json()

    assert body["event_created"] is True
    assert body["already_existed"] is False
    assert body["new_customer_count"] == 2
    assert body["event_id"] == "evt123"
    assert body["event_link"] == "https://calendar.google.com/event?eid=evt123"
    assert {c["email"] for c in body["new_customers"]} == {"new1@example.com", "new2@example.com"}

    # The event is scheduled EVENT_OFFSET_DAYS out, not today.
    assert body["event_start"] is not None
    event_date = body["event_start"][:10]
    assert event_date != body["date"]

    # The Calendar API was called exactly once, with both customers listed
    # in the description, and a marker so a later call can detect it.
    assert len(calls) == 1
    description = calls[0]["description"]
    assert "New Customer One" in description
    assert "new1@example.com" in description
    assert "New Customer Two" in description
    assert "new2@example.com" in description
    assert calls[0]["extended_properties"]  # the dedupe marker was attached


# ---------------------------------------------------------------------------
# Calling it twice for the same day -> second call finds the existing event
# instead of creating a duplicate
# ---------------------------------------------------------------------------

def test_second_call_same_day_does_not_duplicate_event(client, db_session, monkeypatch):
    _create_customer(db_session, "new4@example.com", "New Customer Four")

    monkeypatch.setattr(
        customer_care_service.calendar_service,
        "find_event_by_private_property",
        lambda **kwargs: {"id": "existing-evt", "htmlLink": "https://calendar.google.com/existing"},
    )

    create_calls = []
    monkeypatch.setattr(
        customer_care_service.calendar_service,
        "create_event",
        lambda **kwargs: create_calls.append(kwargs),
    )

    response = client.post(ENDPOINT, headers={"X-API-Key": TEST_PUBLIC_API_KEY})
    assert response.status_code == 200
    body = response.json()

    assert body["event_created"] is False
    assert body["already_existed"] is True
    assert body["event_id"] == "existing-evt"
    assert body["event_link"] == "https://calendar.google.com/existing"
    assert create_calls == []  # no duplicate was created


# ---------------------------------------------------------------------------
# Calendar not configured -> 503, not a crash
# ---------------------------------------------------------------------------

def test_calendar_config_error_returns_503(client, db_session, monkeypatch):
    _create_customer(db_session, "new3@example.com", "New Customer Three")
    _stub_no_existing_event(monkeypatch)

    def raise_config_error(**kwargs):
        raise CalendarConfigError("GOOGLE_CALENDAR_ID is not set in .env.")

    monkeypatch.setattr(customer_care_service.calendar_service, "create_event", raise_config_error)

    response = client.post(ENDPOINT, headers={"X-API-Key": TEST_PUBLIC_API_KEY})
    assert response.status_code == 503
    assert "GOOGLE_CALENDAR_ID" in response.json()["detail"]


def test_calendar_lookup_error_returns_503(client, db_session, monkeypatch):
    """A failure during the duplicate-check itself is also a clean 503."""
    _create_customer(db_session, "new5@example.com", "New Customer Five")

    def raise_config_error(**kwargs):
        raise CalendarConfigError("Google Calendar API request failed (404): Not Found")

    monkeypatch.setattr(
        customer_care_service.calendar_service, "find_event_by_private_property", raise_config_error
    )

    response = client.post(ENDPOINT, headers={"X-API-Key": TEST_PUBLIC_API_KEY})
    assert response.status_code == 503
