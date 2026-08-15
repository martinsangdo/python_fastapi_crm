"""
google_calendar_service.py
----------------------------
Talks to the Google Calendar API using a SERVICE ACCOUNT (no human login
flow, no browser redirect) — the standard way for a server-to-server job
like the daily "new customers" check (service/customer_care_service.py) to
create calendar events on its own.

--------------------------------------------------------------------------
ONE-TIME SETUP (Google Cloud Console)
--------------------------------------------------------------------------
1. Create (or pick) a Google Cloud project, then enable the
   "Google Calendar API" for it (APIs & Services -> Enable APIs).
2. Create a Service Account (IAM & Admin -> Service Accounts -> Create),
   then open it -> Keys -> Add Key -> Create new key -> JSON. This
   downloads a JSON key file.
3. Save that file inside this project (see GOOGLE_SERVICE_ACCOUNT_FILE
   below). It is already covered by .gitignore's `*.json` rule, so it will
   not be committed — never commit it.
4. Open the Google Calendar you want events created on (in a real Google
   account, e.g. the sales team's calendar) -> Settings and sharing ->
   "Share with specific people or groups" -> add the service account's
   email (it looks like xxxxx@yyyyy.iam.gserviceaccount.com — find it in
   the JSON key file's "client_email" field) with "Make changes to events".
5. On that same settings page, scroll to "Integrate calendar" and copy the
   "Calendar ID" (for a personal calendar this is usually just the owner's
   email address) into GOOGLE_CALENDAR_ID in .env.

   IMPORTANT: do NOT use "primary" as the calendar id. "primary" would mean
   the SERVICE ACCOUNT's own calendar, which is a hidden calendar no human
   can see — you must use the real, shared calendar's id from step 5.
--------------------------------------------------------------------------
"""

import os
from datetime import datetime
from typing import Optional

from dotenv import load_dotenv
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Load GOOGLE_SERVICE_ACCOUNT_FILE / GOOGLE_CALENDAR_ID from .env.
load_dotenv()

# The one permission scope this app needs: read/write access to events.
_SCOPES = ["https://www.googleapis.com/auth/calendar"]

GOOGLE_SERVICE_ACCOUNT_FILE = os.getenv(
    "GOOGLE_SERVICE_ACCOUNT_FILE", "google-service-account.json"
)
GOOGLE_CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID")


class CalendarConfigError(Exception):
    """
    Raised when the Calendar integration isn't set up correctly: the service
    account file or calendar id is missing, OR Google rejected the request
    (e.g. the calendar hasn't been shared with the service account yet).
    Callers (routers/tasks.py) map this to a 503 with the message as-is.
    """


def _get_service():
    """Build an authenticated Calendar API client, or raise CalendarConfigError."""
    if not GOOGLE_CALENDAR_ID:
        raise CalendarConfigError("GOOGLE_CALENDAR_ID is not set in .env.")
    if not os.path.exists(GOOGLE_SERVICE_ACCOUNT_FILE):
        raise CalendarConfigError(
            f"Service account key file not found at '{GOOGLE_SERVICE_ACCOUNT_FILE}'. "
            "Set GOOGLE_SERVICE_ACCOUNT_FILE in .env, or place the downloaded "
            "JSON key at that path. See the setup notes at the top of this file."
        )
    credentials = service_account.Credentials.from_service_account_file(
        GOOGLE_SERVICE_ACCOUNT_FILE, scopes=_SCOPES
    )
    # cache_discovery=False avoids a noisy warning about the discovery cache
    # (which needs a writable temp dir we don't otherwise use).
    return build("calendar", "v3", credentials=credentials, cache_discovery=False)


def _service_account_email() -> str:
    """The service account's own email, for error messages (see below)."""
    try:
        credentials = service_account.Credentials.from_service_account_file(
            GOOGLE_SERVICE_ACCOUNT_FILE, scopes=_SCOPES
        )
        return credentials.service_account_email
    except Exception:
        return f"the client_email in {GOOGLE_SERVICE_ACCOUNT_FILE}"


def _as_config_error(error: HttpError) -> CalendarConfigError:
    """
    Translate a raw Google API error into a CalendarConfigError with an
    actionable message, instead of letting a stack trace leak out as a 500.
    """
    if error.resp.status == 404:
        # Google returns 404 (not 403) when the service account can see the
        # API but hasn't been granted access to THIS calendar — it never
        # reveals whether a calendar exists to someone without access. This
        # is by far the most common setup mistake.
        client_email = _service_account_email()
        return CalendarConfigError(
            f"Google Calendar returned 404 Not Found for calendar "
            f"'{GOOGLE_CALENDAR_ID}'. This almost always means the calendar "
            f"has not been shared with the service account ({client_email}). "
            f"Open the calendar's sharing settings, add that email with "
            f"'Make changes to events' permission, and try again."
        )
    return CalendarConfigError(
        f"Google Calendar API request failed ({error.resp.status}): {error.reason}"
    )


def find_event_by_private_property(
    *, key: str, value: str, time_min: datetime, time_max: datetime
) -> Optional[dict]:
    """
    Look up an existing event carrying extendedProperties.private[key] ==
    value, within [time_min, time_max). Used to avoid creating a DUPLICATE
    event if a task is triggered more than once for the same day (e.g. a
    scheduler retry, or someone calling the endpoint twice by hand).

    Returns the event resource dict, or None if no such event exists yet.
    `time_min`/`time_max` must be timezone-aware datetimes.
    """
    service = _get_service()
    try:
        response = (
            service.events()
            .list(
                calendarId=GOOGLE_CALENDAR_ID,
                privateExtendedProperty=f"{key}={value}",
                timeMin=time_min.isoformat(),
                timeMax=time_max.isoformat(),
                singleEvents=True,
                maxResults=1,
            )
            .execute()
        )
    except HttpError as error:
        raise _as_config_error(error) from error
    items = response.get("items", [])
    return items[0] if items else None


def create_event(
    *,
    summary: str,
    description: str,
    start: datetime,
    end: datetime,
    timezone: str,
    extended_properties: Optional[dict] = None,
) -> dict:
    """
    Create one event on the configured calendar and return the API's event
    resource (a dict that includes "id" and "htmlLink").

    `start` and `end` must be timezone-aware datetimes. `extended_properties`,
    if given, is stored as the event's private extended properties — a
    stable marker a later call can look up via find_event_by_private_property
    to avoid creating a duplicate.
    """
    service = _get_service()
    body = {
        "summary": summary,
        "description": description,
        "start": {"dateTime": start.isoformat(), "timeZone": timezone},
        "end": {"dateTime": end.isoformat(), "timeZone": timezone},
    }
    if extended_properties:
        body["extendedProperties"] = {"private": extended_properties}
    try:
        return service.events().insert(calendarId=GOOGLE_CALENDAR_ID, body=body).execute()
    except HttpError as error:
        raise _as_config_error(error) from error
