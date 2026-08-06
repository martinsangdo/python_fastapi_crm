import os
import json
import re
import calendar
from datetime import date, datetime
from typing import List, Dict, Any, Optional

import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv
from groq import Groq

# Load environment variables from .env file
load_dotenv()

# ==============================================================================
# CONFIGURATION & CONSTANTS
# ==============================================================================
DEFAULT_SHEET_ID = "13uvwmvSUEw8Hi2AdF-12gPEidqI75eNfOXffA0eevG0"
GROQ_MODEL = "llama-3.3-70b-versatile"  # High performance model with strong tool-calling support

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]

# Page configuration
st.set_page_config(
    page_title="Sheets Virtual Assistant (MCP + Groq)",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ==============================================================================
# MCP TOOL DEFINITIONS (Model Context Protocol Layer)
# ==============================================================================
class GoogleSheetsMCPServer:
    """
    Implements an MCP-compatible Tool Provider for Google Sheets.
    Exposes explicit schema definitions and executable handlers.
    """
    def __init__(self, sheet_id: str, credentials_dict: Optional[dict] = None, api_key: Optional[str] = None):
        self.sheet_id = sheet_id
        self.client = self._init_gspread_client(credentials_dict, api_key)

    def _init_gspread_client(self, credentials_dict: Optional[dict] = None, api_key: Optional[str] = None) -> Optional[gspread.Client]:
        """Authenticates with Google Sheets API.

        Tries, in order: an uploaded service account file, a Google API key
        (read-only, works for publicly shared sheets, no OAuth setup needed),
        a service account in st.secrets, then a local credentials.json.
        """
        # st.secrets raises if no secrets.toml exists anywhere - that's a normal
        # setup for a public sheet, not an error, so check for it safely.
        try:
            has_secrets_service_account = "gcp_service_account" in st.secrets
        except Exception:
            has_secrets_service_account = False

        try:
            if credentials_dict:
                creds = Credentials.from_service_account_info(credentials_dict, scopes=SCOPES)
                return gspread.authorize(creds)
            elif api_key:
                # Read-only access to publicly shared sheets - no service account required.
                return gspread.api_key(api_key)
            elif has_secrets_service_account:
                creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=SCOPES)
                return gspread.authorize(creds)
            elif os.path.exists("credentials.json"):
                creds = Credentials.from_service_account_file("credentials.json", scopes=SCOPES)
                return gspread.authorize(creds)
            else:
                return None
        except Exception as e:
            st.error(f"Google Auth Error: {str(e)}")
            return None

    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        """Returns MCP-compliant tool specifications formatted for Groq / OpenAI spec."""
        return [
            {
                "type": "function",
                "function": {
                    "name": "get_sheet_metadata",
                    "description": "Get metadata about all worksheets, column names, and row counts in the Google Sheet.",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": [],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "read_sheet_data",
                    "description": "Fetch all rows from a specific worksheet as structured JSON records.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "worksheet_name": {
                                "type": "string",
                                "description": "The exact name of the worksheet tab to read.",
                            },
                            "limit": {
                                "type": "integer",
                                "description": "Maximum number of rows to retrieve (default: 100).",
                            },
                        },
                        "required": ["worksheet_name"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "search_data",
                    "description": "Filter worksheet rows matching a specific search keyword across columns.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "worksheet_name": {
                                "type": "string",
                                "description": "The worksheet to search within.",
                            },
                            "query": {
                                "type": "string",
                                "description": "Search keyword or term to match.",
                            },
                        },
                        "required": ["worksheet_name", "query"],
                    },
                },
            },
        ]

    def _resolve_worksheet(self, doc, ws_name: str):
        """Finds a worksheet by name, tolerating case differences and partial matches.

        The Groq model sometimes guesses a worksheet name (e.g. "Rooms") that's close
        but not identical to the real tab title. Falling straight through to
        doc.worksheet() would raise WorksheetNotFound on any mismatch, so try looser
        matches first and only fail with the real list of tabs as a last resort.
        """
        try:
            return doc.worksheet(ws_name)
        except gspread.exceptions.WorksheetNotFound:
            pass

        all_worksheets = doc.worksheets()
        lowered = ws_name.strip().lower()

        for ws in all_worksheets:
            if ws.title.strip().lower() == lowered:
                return ws

        for ws in all_worksheets:
            if lowered in ws.title.strip().lower() or ws.title.strip().lower() in lowered:
                return ws

        # A single-tab sheet has no ambiguity - use it regardless of what name was guessed.
        if len(all_worksheets) == 1:
            return all_worksheets[0]

        available = [ws.title for ws in all_worksheets]
        raise ValueError(f"No worksheet named '{ws_name}' found. Available worksheets: {available}")

    @staticmethod
    def _get_worksheet_records(ws) -> List[Dict[str, Any]]:
        """Reads a worksheet as row dicts without gspread's get_all_records().

        get_all_records() raises if the header row has duplicate cells (very common
        with trailing blank/formatted columns, which show up as duplicate '' headers).
        Reading raw values and trimming trailing blank header columns ourselves avoids
        that entirely.
        """
        values = ws.get_all_values()
        if not values:
            return []

        headers = list(values[0])
        while headers and headers[-1] == "":
            headers.pop()

        records = []
        for row in values[1:]:
            row = row[:len(headers)]
            row += [""] * (len(headers) - len(row))
            records.append(dict(zip(headers, row)))
        return records

    # --- Tool Implementations ---
    def execute_tool(self, name: str, arguments: Dict[str, Any]) -> str:
        if not self.client:
            return json.dumps({"error": "Google Sheets client not authenticated. Please check service account credentials."})

        try:
            doc = self.client.open_by_key(self.sheet_id)

            if name == "get_sheet_metadata":
                sheets_info = []
                for ws in doc.worksheets():
                    records = ws.get_all_values()
                    headers = records[0] if records else []
                    sheets_info.append({
                        "worksheet_title": ws.title,
                        "row_count": len(records) - 1 if len(records) > 0 else 0,
                        "columns": headers
                    })
                return json.dumps({"spreadsheet_title": doc.title, "worksheets": sheets_info})

            elif name == "read_sheet_data":
                ws_name = arguments.get("worksheet_name")
                limit = arguments.get("limit", 100)
                ws = self._resolve_worksheet(doc, ws_name)
                data = self._get_worksheet_records(ws)[:limit]
                return json.dumps({"worksheet": ws.title, "record_count": len(data), "data": data})

            elif name == "search_data":
                ws_name = arguments.get("worksheet_name")
                query = str(arguments.get("query", "")).lower()
                ws = self._resolve_worksheet(doc, ws_name)
                all_data = self._get_worksheet_records(ws)
                
                filtered = [
                    row for row in all_data 
                    if any(query in str(val).lower() for val in row.values())
                ]
                return json.dumps({"worksheet": ws.title, "query": query, "matches_found": len(filtered), "data": filtered})

            else:
                return json.dumps({"error": f"Unknown MCP tool: {name}"})

        except Exception as e:
            return json.dumps({"error": f"Failed to execute tool '{name}': {str(e)}"})


# ==============================================================================
# AGENT ORCHESTRATOR (GROQ INTEGRATION)
# ==============================================================================
KNOWN_TOOL_NAMES = {"get_sheet_metadata", "read_sheet_data", "search_data"}

# Llama 3.3 on Groq occasionally emits a malformed pseudo tool-call as plain text
# instead of a structured tool_calls entry - Groq's parser doesn't recognize the
# malformed tag and passes it through as ordinary content. The exact shape varies
# ("<function>get_all_records</function>{...}", "<function>get_data(range=...)</function>",
# etc.) and the model sometimes invents tool names/argument styles that don't match
# our actual schema at all. FUNCTION_TAG_PATTERN just detects "some kind of function
# tag is present" broadly; PSEUDO_FUNCTION_CALL_PATTERN additionally tries to extract
# real JSON arguments when they happen to be in that shape.
FUNCTION_TAG_PATTERN = re.compile(r"<function[=>]", re.IGNORECASE)
PSEUDO_FUNCTION_CALL_PATTERN = re.compile(
    r"<function[=>]\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*>?\s*(?:</function>)?\s*(\{.*\})\s*(?:</function>)?",
    re.DOTALL,
)


class MCPAgent:
    """Agent that bridges user queries, Groq API, and MCP Google Sheets Tool Server."""
    def __init__(self, api_key: str, mcp_server: GoogleSheetsMCPServer):
        # Initialize the Groq client
        self.llm_client = Groq(api_key=api_key)
        self.mcp_server = mcp_server

    @staticmethod
    def _parse_pseudo_function_call(content: str) -> Optional[tuple]:
        """Best-effort extraction of (tool_name, arguments) from malformed tool-call text."""
        match = PSEUDO_FUNCTION_CALL_PATTERN.search(content)
        if not match:
            return None
        name, args_blob = match.group(1), match.group(2)
        try:
            args = json.loads(args_blob)
        except json.JSONDecodeError:
            return None
        return name, args

    @staticmethod
    def _is_malformed(content: Optional[str]) -> bool:
        return bool(content) and bool(FUNCTION_TAG_PATTERN.search(content))

    def _deterministic_recovery_call(self) -> tuple:
        """Ignores whatever the model tried to invent and just pulls real data.

        Used when a malformed pseudo tool-call can't be safely parsed (unknown
        arg syntax, fabricated tool semantics like spreadsheet A1 ranges). Rather
        than guess the model's intent, fetch metadata for the actual worksheet
        name, then read its full data - the next round can then answer from real
        rows instead of repeating the same malformed text.
        """
        metadata_json = self.mcp_server.execute_tool("get_sheet_metadata", {})
        try:
            worksheets = json.loads(metadata_json).get("worksheets", [])
        except json.JSONDecodeError:
            worksheets = []
        ws_name = worksheets[0]["worksheet_title"] if worksheets else ""
        return "read_sheet_data", {"worksheet_name": ws_name}

    @staticmethod
    def _fallback_answer_from_result(result: str) -> str:
        """Formats a tool result as plain text without the model's help.

        Used only when even the synthesis pass emits the malformed pseudo tool-call
        text, so a garbled answer never reaches the user or gets saved into chat
        history (where it would otherwise poison every future turn).
        """
        try:
            data = json.loads(result)
        except json.JSONDecodeError:
            return "I retrieved the data but couldn't format a response. Please try rephrasing your question."
        if "error" in data:
            return f"I couldn't retrieve that data: {data['error']}"
        rows = data.get("data", [])
        worksheet = data.get("worksheet", "")
        if not rows:
            return f"No matching rows found in worksheet '{worksheet}'."
        lines = [f"Found {len(rows)} row(s) in '{worksheet}':"]
        for row in rows[:20]:
            lines.append("- " + ", ".join(f"{k}: {v}" for k, v in row.items()))
        return "\n".join(lines)

    def run(self, messages: List[Dict[str, Any]], max_rounds: int = 4) -> str:
        """Executes a multi-round Tool-Use loop with Groq.

        The model often needs more than one tool call per question - e.g. it checks
        get_sheet_metadata first (per the system prompt) and only then knows which
        worksheet/columns to query with search_data. A single-shot "call tools once,
        then synthesize" flow would strand it after the metadata call with no actual
        row data, producing confident-sounding but wrong answers. So this loops,
        feeding each tool result back, until the model stops requesting tools.
        """
        tools = self.mcp_server.get_tool_definitions()

        system_prompt = {
            "role": "system",
            "content": (
                "You are an expert Virtual Data Assistant operating over a Google Sheet using the Model Context Protocol (MCP).\n"
                "Rules:\n"
                "1. Always check the available worksheets/metadata first if you are unsure of the data structure.\n"
                "2. Then call read_sheet_data or search_data to retrieve the actual rows before answering - "
                "never answer from metadata (column names) alone.\n"
                "3. Base your final answers directly on retrieved row data. Be precise, clear, and concise."
            )
        }

        conversation = [system_prompt] + messages
        last_result = None

        for _ in range(max_rounds):
            response = self.llm_client.chat.completions.create(
                model=GROQ_MODEL,
                messages=conversation,
                tools=tools,
                tool_choice="auto",
                temperature=0.1
            )
            response_message = response.choices[0].message

            calls = [
                (tc.id, tc.function.name,
                 json.loads(tc.function.arguments) if isinstance(tc.function.arguments, str) else tc.function.arguments)
                for tc in (response_message.tool_calls or [])
            ]

            # Fall back to parsing a malformed pseudo tool-call as a real one.
            assistant_content = response_message.content
            if not calls and response_message.content:
                parsed = self._parse_pseudo_function_call(response_message.content)
                if parsed:
                    fn_name, fn_args = parsed
                    calls = [(f"pseudo_{len(conversation)}", fn_name, fn_args)]
                    # Don't echo the malformed text back into the model's own context -
                    # it tends to reinforce the same broken formatting on the next round.
                    assistant_content = None
                elif self._is_malformed(response_message.content):
                    # Some malformed shape we can't parse args out of (unknown arg
                    # syntax, fabricated tool/params) - don't guess, just fetch real data.
                    fn_name, fn_args = self._deterministic_recovery_call()
                    calls = [(f"pseudo_{len(conversation)}", fn_name, fn_args)]
                    assistant_content = None

            if not calls:
                if self._is_malformed(response_message.content):
                    if last_result is not None:
                        return self._fallback_answer_from_result(last_result)
                    return "I had trouble understanding your question well enough to query the sheet. Could you rephrase it?"
                return response_message.content

            conversation.append({
                "role": "assistant",
                "content": assistant_content,
                "tool_calls": [
                    {
                        "id": call_id,
                        "type": "function",
                        "function": {"name": fn_name, "arguments": json.dumps(fn_args)}
                    }
                    for call_id, fn_name, fn_args in calls
                ]
            })

            for call_id, fn_name, fn_args in calls:
                # The model sometimes names an underlying gspread method (e.g.
                # get_all_records) instead of one of our actual tools - read_sheet_data
                # is the closest equivalent for any unrecognized name.
                if fn_name not in KNOWN_TOOL_NAMES:
                    fn_name = "read_sheet_data"

                with st.spinner(f"⚡ MCP Tool Executing via Groq: `{fn_name}`..."):
                    result = self.mcp_server.execute_tool(fn_name, fn_args)
                last_result = result

                conversation.append({
                    "role": "tool",
                    "tool_call_id": call_id,
                    "name": fn_name,
                    "content": result
                })

        # Exhausted max_rounds without a final answer - synthesize from the last data we got.
        if last_result is not None:
            return self._fallback_answer_from_result(last_result)
        return "I couldn't get a clear answer from the sheet. Could you rephrase your question?"


# ==============================================================================
# ROOM OCCUPANCY CALENDAR
# ==============================================================================
def _find_column(row: Dict[str, Any], *candidates: str) -> Optional[str]:
    """Case-insensitive lookup of a column name that may vary between sheets (e.g. 'CheckIn' vs 'Check-in')."""
    lowered = {k.strip().lower(): k for k in row.keys()}
    for candidate in candidates:
        key = lowered.get(candidate.lower())
        if key is not None:
            return key
    return None


def _parse_date(value: Any) -> Optional[date]:
    value = str(value).strip()
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def get_occupancy_events(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Builds {room, check_in, check_out} entries for bookings that actually occupy a room.

    A booking occupies its room for every night from check-in up to (but not including)
    check-out. Cancelled bookings never occupy a room, regardless of their dates.
    """
    if not records:
        return []

    sample = records[0]
    checkin_col = _find_column(sample, "CheckIn", "Check In", "Check-in")
    checkout_col = _find_column(sample, "CheckOut", "Check Out", "Check-out")
    room_col = _find_column(sample, "Room", "Room Number", "RoomNumber")
    status_col = _find_column(sample, "Status")

    if not (checkin_col and checkout_col and room_col):
        return []

    events = []
    for row in records:
        status = str(row.get(status_col, "")).strip().lower() if status_col else ""
        if status == "cancelled":
            continue

        check_in = _parse_date(row.get(checkin_col, ""))
        check_out = _parse_date(row.get(checkout_col, ""))
        room = str(row.get(room_col, "")).strip()

        if check_in and check_out and room:
            events.append({"room": room, "check_in": check_in, "check_out": check_out})

    return events


def get_occupied_rooms_by_day(events: List[Dict[str, Any]], year: int, month: int) -> Dict[int, List[str]]:
    """Maps each day-of-month to the list of rooms occupied that night."""
    _, days_in_month = calendar.monthrange(year, month)
    occupied: Dict[int, List[str]] = {}

    for day_num in range(1, days_in_month + 1):
        current = date(year, month, day_num)
        rooms_today = sorted({e["room"] for e in events if e["check_in"] <= current < e["check_out"]})
        if rooms_today:
            occupied[day_num] = rooms_today

    return occupied


def render_occupancy_calendar(mcp_server: GoogleSheetsMCPServer):
    """Renders a month-view calendar highlighting dates that have occupied rooms."""
    st.subheader("📅 Room Occupancy Calendar")

    if not mcp_server.client:
        st.info("Add a Google API key or service account in the sidebar to see the occupancy calendar.")
        return

    metadata = json.loads(mcp_server.execute_tool("get_sheet_metadata", {}))
    if "error" in metadata:
        st.warning(f"Couldn't load calendar data: {metadata['error']}")
        return

    ws_titles = [ws["worksheet_title"] for ws in metadata.get("worksheets", [])]
    if not ws_titles:
        st.info("This sheet has no worksheets to show.")
        return
    ws_title = ws_titles[0] if len(ws_titles) == 1 else st.selectbox("Worksheet", ws_titles)

    today = date.today()
    col1, col2 = st.columns(2)
    with col1:
        year = int(st.number_input("Year", min_value=2000, max_value=2100, value=today.year, step=1))
    with col2:
        month = st.selectbox(
            "Month", options=list(range(1, 13)), index=today.month - 1,
            format_func=lambda m: calendar.month_name[m]
        )

    data = json.loads(mcp_server.execute_tool("read_sheet_data", {"worksheet_name": ws_title, "limit": 10000}))
    if "error" in data:
        st.warning(f"Couldn't load calendar data: {data['error']}")
        return

    events = get_occupancy_events(data.get("data", []))
    if not events:
        st.info("No CheckIn / CheckOut / Room / Status columns found, or no active bookings in this worksheet.")
        return

    occupied_by_day = get_occupied_rooms_by_day(events, year, month)

    weeks = calendar.Calendar(firstweekday=0).monthdayscalendar(year, month)
    header_cols = st.columns(7)
    for col, label in zip(header_cols, ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]):
        col.markdown(f"**{label}**")

    for week in weeks:
        week_cols = st.columns(7)
        for col, day_num in zip(week_cols, week):
            if day_num == 0:
                col.write("")
                continue
            rooms = occupied_by_day.get(day_num, [])
            with col.container(border=True):
                if rooms:
                    st.markdown(f"**{day_num}** 🔴")
                    st.caption("Room " + ", ".join(rooms))
                else:
                    st.markdown(f"{day_num}")

    st.caption("🔴 = at least one room occupied that night (Cancelled bookings are excluded)")


# ==============================================================================
# STREAMLIT USER INTERFACE
# ==============================================================================
def main():
    st.title("⚡ Intelligent Virtual Assistant (Google Sheets + Groq MCP)")
    st.caption("Powered by Groq Llama 3.3, Model Context Protocol (MCP), and Streamlit")

    # Sidebar: Configurations
    with st.sidebar:
        st.header("⚙️ Configuration")
        
        # Check if GROQ_API_KEY is in .env
        env_groq_key = os.getenv("GROQ_API_KEY", "")
        
        if env_groq_key:
            st.success("🔑 Groq API Key detected from `.env`")
            groq_key = env_groq_key
        else:
            groq_key = st.text_input("Groq API Key", type="password", help="Enter your Groq API Key or place it in .env")
        
        sheet_id = st.text_input("Google Sheet ID", value=DEFAULT_SHEET_ID)
        
        st.markdown("---")
        st.subheader("🔐 Google Credentials")
        st.caption("Sheet is public? Just paste a Google API key below - no service account needed.")

        env_google_api_key = os.getenv("GOOGLE_API_KEY", "")
        if env_google_api_key:
            st.success("🔑 Google API Key detected from `.env`")
            google_api_key = env_google_api_key
        else:
            google_api_key = st.text_input(
                "Google API Key (Optional, for public sheets)",
                type="password",
                help="Create a free API key in Google Cloud Console with the Sheets API enabled. Works read-only for publicly shared sheets.",
            )

        creds_file = st.file_uploader("Upload Service Account JSON (Optional, for private sheets)", type=["json"])

        creds_data = None
        if creds_file:
            try:
                creds_data = json.load(creds_file)
                st.success("Credentials uploaded!")
            except Exception as e:
                st.error("Invalid JSON file")

        st.markdown("---")
        if st.button("Clear Chat History", use_container_width=True):
            st.session_state.messages = []
            st.rerun()

    # Initialize the MCP Server once per rerun - shared by the calendar and the chat agent
    mcp_server = GoogleSheetsMCPServer(sheet_id=sheet_id, credentials_dict=creds_data, api_key=google_api_key)

    render_occupancy_calendar(mcp_server)
    st.markdown("---")

    # Session State Initialization
    if "messages" not in st.session_state:
        st.session_state.messages = []

    # Display Chat History
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # Handle User Input
    if user_prompt := st.chat_input("Ask a question about your Google Sheet data..."):
        if not groq_key:
            st.warning("Please provide a Groq API Key in your `.env` file or sidebar to proceed.")
            st.stop()

        # Add user message to history
        st.session_state.messages.append({"role": "user", "content": user_prompt})
        with st.chat_message("user"):
            st.markdown(user_prompt)

        # Initialize Groq Agent (reuses the MCP Server created above)
        agent = MCPAgent(api_key=groq_key, mcp_server=mcp_server)

        # Generate Assistant Response
        with st.chat_message("assistant"):
            try:
                # Pass chat context to Agent
                history_input = [
                    {"role": m["role"], "content": m["content"]} 
                    for m in st.session_state.messages
                ]
                response_text = agent.run(history_input)
                st.markdown(response_text)
                
                # Append assistant response to chat history
                st.session_state.messages.append({"role": "assistant", "content": response_text})

            except Exception as e:
                st.error(f"Error processing request with Groq: {str(e)}")

# ==============================================================================
# ENTRYPOINT
# ==============================================================================
if __name__ == "__main__":
    main()

#streamlit run app.py