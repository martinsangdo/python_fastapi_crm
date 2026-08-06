import os
import io
import re
import json
from typing import List, Dict, Any, Optional

import streamlit as st
from dotenv import load_dotenv
from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials
from groq import Groq
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from pypdf import PdfReader
import docx

# Load environment variables from .env file
load_dotenv()

# ==============================================================================
# CONFIGURATION & CONSTANTS
# ==============================================================================
DEFAULT_FOLDER_ID = "1sHrT3SIBBDCBwpDSE_eKiLWWQ7OqbFaj"  # paste your public Google Drive folder ID or share link here
GROQ_MODEL = "llama-3.3-70b-versatile"

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

CHUNK_SIZE = 900
CHUNK_OVERLAP = 150

SUPPORTED_MIME_TYPES = {
    "application/vnd.google-apps.document",
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
    "text/markdown",
}

# Page configuration
st.set_page_config(
    page_title="Document Q&A Assistant (Drive + RAG)",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded",
)


def extract_folder_id(value: str) -> str:
    """Accepts either a raw folder ID or a full Drive folder share link and returns just the ID."""
    match = re.search(r"/folders/([a-zA-Z0-9_-]+)", value)
    return match.group(1) if match else value.strip()


# ==============================================================================
# DOCUMENT TEXT EXTRACTION
# ==============================================================================
def _extract_pdf_text(raw: bytes) -> str:
    reader = PdfReader(io.BytesIO(raw))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _extract_docx_text(raw: bytes) -> str:
    document = docx.Document(io.BytesIO(raw))
    return "\n".join(p.text for p in document.paragraphs)


def extract_text(service, file_id: str, mime_type: str) -> Optional[str]:
    """Extracts plain text from a Drive file based on its mime type. Returns None for unsupported/failed files."""
    try:
        if mime_type == "application/vnd.google-apps.document":
            raw = service.files().export(fileId=file_id, mimeType="text/plain").execute()
            return raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
        elif mime_type == "application/pdf":
            raw = service.files().get_media(fileId=file_id).execute()
            return _extract_pdf_text(raw)
        elif mime_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
            raw = service.files().get_media(fileId=file_id).execute()
            return _extract_docx_text(raw)
        elif mime_type in ("text/plain", "text/markdown"):
            raw = service.files().get_media(fileId=file_id).execute()
            return raw.decode("utf-8", errors="ignore") if isinstance(raw, bytes) else str(raw)
        else:
            return None
    except Exception:
        # A single unreadable/corrupt file shouldn't take down the whole index.
        return None


# ==============================================================================
# MCP TOOL DEFINITIONS (RAG over a Google Drive folder)
# ==============================================================================
class DriveRAGServer:
    """MCP-style tool provider that indexes documents from a public Google Drive folder
    and answers retrieval queries against them using TF-IDF similarity (no external
    embeddings API needed, so there's one less thing that can go wrong or cost money).
    """

    def __init__(self, folder_id: str, api_key: Optional[str] = None, credentials_dict: Optional[dict] = None):
        self.folder_id = extract_folder_id(folder_id)
        self.used_service_account = bool(credentials_dict)
        self.service = self._init_drive_service(api_key, credentials_dict)
        self.documents: List[Dict[str, str]] = []   # [{name, text}]
        self.chunks: List[Dict[str, str]] = []       # [{doc_name, text}]
        self.vectorizer = None
        self.chunk_vectors = None
        self.load_error: Optional[str] = None
        self.total_files_found = 0
        self.skipped_files: List[Dict[str, str]] = []  # [{name, reason}]

    def _init_drive_service(self, api_key: Optional[str], credentials_dict: Optional[dict]):
        """Authenticates with Google Drive.

        Unlike the Sheets assistant, a plain API key is NOT enough here: Google blocks the
        files.list call (browsing a folder's contents) for API-key-only requests, even on
        public folders, to prevent anonymous enumeration. A service account is required -
        and reliably listing a folder's children (as opposed to reading one already-known
        file) generally needs the folder explicitly shared with the service account's own
        email address as a Viewer, even when the folder is link-public.
        """
        try:
            if credentials_dict:
                creds = Credentials.from_service_account_info(credentials_dict, scopes=SCOPES)
                return build("drive", "v3", credentials=creds, cache_discovery=False)
            elif api_key:
                return build("drive", "v3", developerKey=api_key, cache_discovery=False)
            else:
                return None
        except Exception as e:
            st.error(f"Google Drive Auth Error: {str(e)}")
            return None

    def load_documents(self) -> None:
        """Fetches and indexes every supported document in the folder. Call once and cache the result."""
        if not self.service or not self.folder_id:
            return

        # Check the folder itself first, separately from listing its children - this tells
        # "the service account can't see the folder at all" apart from "the folder is genuinely
        # empty", which a bare empty files.list() result can't distinguish on its own.
        try:
            folder = self.service.files().get(
                fileId=self.folder_id, fields="id, name, mimeType",
                supportsAllDrives=True,
            ).execute()
            if folder.get("mimeType") != "application/vnd.google-apps.folder":
                self.load_error = (
                    f"The ID/link you gave points to a file called '{folder.get('name')}', not a folder. "
                    "Double check you copied the folder's own share link, not a file inside it."
                )
                return
        except Exception as e:
            self.load_error = (
                f"The service account can't access this folder at all (Google said: {e}). Double check: "
                "(1) the folder ID/link is correct, and (2) you shared the folder with the exact "
                "`client_email` from your service account JSON, as a Viewer."
            )
            return

        try:
            results = self.service.files().list(
                q=f"'{self.folder_id}' in parents and trashed = false",
                fields="files(id, name, mimeType)",
                pageSize=100,
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            ).execute()
            files = results.get("files", [])
        except Exception as e:
            err_text = str(e)
            if "blocked" in err_text.lower() and not self.used_service_account:
                self.load_error = (
                    "Google blocks browsing a folder's contents using only an API key (this is a Google "
                    "Drive restriction, not a bug here) - an API key can only fetch a file whose ID you "
                    "already know, not list what's inside a folder. Upload a free Google service account "
                    "JSON in the sidebar instead, and share the folder with its email address as a Viewer."
                )
            else:
                self.load_error = err_text
            return

        self.total_files_found = len(files)

        for f in files:
            if f["mimeType"] not in SUPPORTED_MIME_TYPES:
                self.skipped_files.append({"name": f["name"], "reason": f"unsupported file type ({f['mimeType']})"})
                continue
            text = extract_text(self.service, f["id"], f["mimeType"])
            if text and text.strip():
                self.documents.append({"name": f["name"], "text": text})
            else:
                self.skipped_files.append({"name": f["name"], "reason": "couldn't extract any text from this file"})

        self._build_index()

    def _build_index(self) -> None:
        self.chunks = [
            {"doc_name": doc["name"], "text": chunk_text}
            for doc in self.documents
            for chunk_text in self._chunk_text(doc["text"])
        ]

        if not self.chunks:
            return

        try:
            self.vectorizer = TfidfVectorizer(stop_words="english")
            self.chunk_vectors = self.vectorizer.fit_transform([c["text"] for c in self.chunks])
        except ValueError:
            # e.g. every chunk turned out to be only stop-words - leave unindexed rather than crash.
            self.vectorizer = None
            self.chunk_vectors = None

    @staticmethod
    def _chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> List[str]:
        text = " ".join(text.split())
        if not text:
            return []
        chunks = []
        start = 0
        while start < len(text):
            chunks.append(text[start:start + size])
            start += size - overlap
        return chunks

    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        """Returns MCP-compliant tool specifications formatted for Groq / OpenAI spec."""
        return [
            {
                "type": "function",
                "function": {
                    "name": "list_documents",
                    "description": "Lists the titles of every document found in the Google Drive folder.",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "search_documents",
                    "description": "Searches the indexed documents for passages relevant to a query.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "What to search for."},
                            "top_k": {"type": "integer", "description": "Number of passages to return (default 5)."},
                        },
                        "required": ["query"],
                    },
                },
            },
        ]

    # --- Tool Implementations ---
    def execute_tool(self, name: str, arguments: Dict[str, Any]) -> str:
        if not self.service:
            return json.dumps({"error": "Google Drive client not authenticated. Add a Google API key or service account in the sidebar."})
        if self.load_error:
            return json.dumps({"error": f"Couldn't read the Drive folder: {self.load_error}"})
        if not self.documents:
            return json.dumps({"error": "No supported documents were found in this folder (supported: Google Docs, PDF, DOCX, TXT)."})

        try:
            if name == "list_documents":
                return json.dumps({"documents": [d["name"] for d in self.documents]})

            elif name == "search_documents":
                query = str(arguments.get("query", "")).strip()
                top_k = int(arguments.get("top_k", 5))
                if not query or self.vectorizer is None:
                    return json.dumps({"query": query, "results": []})

                query_vec = self.vectorizer.transform([query])
                scores = cosine_similarity(query_vec, self.chunk_vectors)[0]
                ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]

                results = [
                    {
                        "document": self.chunks[i]["doc_name"],
                        "excerpt": self.chunks[i]["text"],
                        "relevance": round(float(scores[i]), 3),
                    }
                    for i in ranked if scores[i] > 0
                ]
                return json.dumps({"query": query, "results": results})

            else:
                return json.dumps({"error": f"Unknown MCP tool: {name}"})

        except Exception as e:
            return json.dumps({"error": f"Failed to execute tool '{name}': {str(e)}"})


# ==============================================================================
# AGENT ORCHESTRATOR (GROQ INTEGRATION)
# ==============================================================================
KNOWN_TOOL_NAMES = {"list_documents", "search_documents"}

# Llama 3.3 on Groq occasionally emits a malformed pseudo tool-call as plain text
# instead of a structured tool_calls entry, with formats and even tool names that
# vary unpredictably. Rather than try to parse every possible malformed shape, we
# detect that "something function-call-shaped happened", try the common JSON-args
# shape, and otherwise fall back to a deterministic real search instead of guessing.
FUNCTION_TAG_PATTERN = re.compile(r"<function[=>]", re.IGNORECASE)
PSEUDO_FUNCTION_CALL_PATTERN = re.compile(
    r"<function[=>]\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*>?\s*(?:</function>)?\s*(\{.*\})\s*(?:</function>)?",
    re.DOTALL,
)


class RAGAgent:
    """Agent that bridges user questions, Groq API, and the Drive-based RAG tool server."""

    def __init__(self, api_key: str, rag_server: DriveRAGServer):
        self.llm_client = Groq(api_key=api_key)
        self.rag_server = rag_server

    @staticmethod
    def _parse_pseudo_function_call(content: str) -> Optional[tuple]:
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

    @staticmethod
    def _fallback_answer_from_result(result: str) -> str:
        """Formats a tool result as plain text without the model's help - used only when
        even the synthesis pass emits malformed text, so garbled output never reaches the
        user or gets saved into chat history (where it would poison every future turn)."""
        try:
            data = json.loads(result)
        except json.JSONDecodeError:
            return "I found some information but couldn't format a response. Please try rephrasing your question."
        if "error" in data:
            return f"I couldn't search the documents: {data['error']}"
        results = data.get("results", [])
        if not results:
            return "I couldn't find anything relevant to that question in the documents."
        lines = ["Here's what I found:"]
        for r in results[:5]:
            lines.append(f"- From \"{r['document']}\": {r['excerpt'][:300]}...")
        return "\n".join(lines)

    @staticmethod
    def _last_user_message(conversation: List[Dict[str, Any]]) -> str:
        for msg in reversed(conversation):
            if msg.get("role") == "user" and isinstance(msg.get("content"), str):
                return msg["content"]
        return ""

    def _deterministic_recovery_call(self, conversation: List[Dict[str, Any]]) -> tuple:
        """Ignores whatever the model tried to invent and just searches with the user's
        own question - safer than guessing at a malformed tool call's intent."""
        return "search_documents", {"query": self._last_user_message(conversation), "top_k": 5}

    def run(self, messages: List[Dict[str, Any]], max_rounds: int = 4) -> str:
        """Executes a multi-round Tool-Use loop with Groq.

        The model often needs more than one tool call per question - e.g. it lists
        documents first and only then knows what to search for. A single-shot flow
        would strand it after list_documents with no actual passages, producing
        confident-sounding but wrong answers. So this loops until the model stops
        requesting tools.
        """
        tools = self.rag_server.get_tool_definitions()

        system_prompt = {
            "role": "system",
            "content": (
                "You are a helpful Document Q&A Assistant that answers questions using only the documents "
                "found in a Google Drive folder, accessed through MCP tools.\n"
                "Rules:\n"
                "1. Use search_documents to find relevant passages before answering - never answer from "
                "memory or from a document list alone.\n"
                "2. If the documents don't contain the answer, say so clearly instead of guessing.\n"
                "3. Mention which document(s) you used. Be precise and concise."
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

            assistant_content = response_message.content
            if not calls and response_message.content:
                parsed = self._parse_pseudo_function_call(response_message.content)
                if parsed:
                    fn_name, fn_args = parsed
                    calls = [(f"pseudo_{len(conversation)}", fn_name, fn_args)]
                    assistant_content = None
                elif self._is_malformed(response_message.content):
                    fn_name, fn_args = self._deterministic_recovery_call(conversation)
                    calls = [(f"pseudo_{len(conversation)}", fn_name, fn_args)]
                    assistant_content = None

            if not calls:
                if self._is_malformed(response_message.content):
                    if last_result is not None:
                        return self._fallback_answer_from_result(last_result)
                    return "I had trouble understanding your question well enough to search the documents. Could you rephrase it?"
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
                # The model occasionally names a tool that doesn't exist in our schema -
                # search_documents is the closest equivalent for any unrecognized name.
                if fn_name not in KNOWN_TOOL_NAMES:
                    fn_name = "search_documents"

                with st.spinner(f"📚 Running MCP tool: `{fn_name}`..."):
                    result = self.rag_server.execute_tool(fn_name, fn_args)
                last_result = result

                conversation.append({
                    "role": "tool",
                    "tool_call_id": call_id,
                    "name": fn_name,
                    "content": result
                })

        if last_result is not None:
            return self._fallback_answer_from_result(last_result)
        return "I couldn't get a clear answer from the documents. Could you rephrase your question?"


# ==============================================================================
# STREAMLIT USER INTERFACE
# ==============================================================================
@st.cache_resource(show_spinner="📂 Loading and indexing documents from Google Drive...")
def load_rag_server(folder_input: str, api_key: str, credentials_dict: Optional[dict]) -> DriveRAGServer:
    server = DriveRAGServer(folder_id=folder_input, api_key=api_key, credentials_dict=credentials_dict)
    server.load_documents()
    return server


def main():
    st.title("📚 Document Q&A Assistant (Google Drive + RAG)")
    st.caption("Ask questions about documents in a public Google Drive folder - powered by Groq Llama 3.3 and MCP-style tools")

    with st.sidebar:
        st.header("⚙️ Configuration")

        env_groq_key = os.getenv("GROQ_API_KEY", "")
        if env_groq_key:
            st.success("🔑 Groq API Key detected from `.env`")
            groq_key = env_groq_key
        else:
            groq_key = st.text_input("Groq API Key", type="password", help="Enter your Groq API Key or place it in .env")

        folder_input = st.text_input(
            "Google Drive Folder (ID or link)",
            value=DEFAULT_FOLDER_ID,
            help="Paste the public folder's share link or just its ID.",
        )

        st.markdown("---")
        st.subheader("🔐 Google Credentials")
        st.caption(
            "Google requires a service account to *browse a folder's contents* - a plain API "
            "key can only fetch a file whose ID you already know, not list what's inside a "
            "folder (this is a Drive API restriction, not something this app can work around). "
            "The folder also needs to be explicitly shared with the service account's own "
            "email address as a Viewer - being 'public' isn't enough for programmatic listing."
        )

        with st.expander("How do I get a service account JSON? (one-time, ~3 min)"):
            st.markdown(
                "1. Go to [Google Cloud Console](https://console.cloud.google.com/) and create a project "
                "(or use an existing one).\n"
                "2. Search for **Google Drive API** and click **Enable**.\n"
                "3. Go to **APIs & Services → Credentials → Create Credentials → Service Account**. "
                "Give it any name and finish the wizard.\n"
                "4. Open the new service account, go to the **Keys** tab, click **Add Key → Create new key → JSON**. "
                "A `.json` file downloads automatically - upload it below.\n"
                "5. **Important:** open that JSON file in a text editor, copy the `client_email` value "
                "(looks like `xxx@xxx.iam.gserviceaccount.com`). Open your Drive folder → Share → paste that "
                "email address → set it to **Viewer** → Send. Without this step the folder will show up empty."
            )

        creds_file = st.file_uploader("Upload Service Account JSON (Required)", type=["json"])
        creds_data = None
        if creds_file:
            try:
                creds_data = json.load(creds_file)
                st.success("Credentials uploaded!")
            except Exception:
                st.error("Invalid JSON file")

        with st.expander("Advanced: Google API Key"):
            st.caption("Only useful if a future version adds direct file-ID lookups - not enough to browse a folder today.")
            env_google_api_key = os.getenv("GOOGLE_API_KEY", "")
            if env_google_api_key:
                st.success("🔑 Google API Key detected from `.env`")
                google_api_key = env_google_api_key
            else:
                google_api_key = st.text_input("Google API Key (Optional)", type="password")

        st.markdown("---")
        if st.button("🔄 Refresh Documents", use_container_width=True):
            st.cache_resource.clear()
            st.rerun()
        if st.button("Clear Chat History", use_container_width=True):
            st.session_state.messages = []
            st.rerun()

    if not folder_input:
        st.info("Add your public Google Drive folder (ID or link) in the sidebar to get started.")
        st.stop()

    if not creds_data:
        st.info("Upload a free Google service account JSON in the sidebar to browse the folder's files.")
        st.stop()

    rag_server = load_rag_server(folder_input, google_api_key, creds_data)

    with st.expander(f"📄 Indexed Documents ({len(rag_server.documents)})", expanded=(not rag_server.documents)):
        if rag_server.load_error:
            st.error(rag_server.load_error)
        elif rag_server.total_files_found == 0:
            st.warning(
                "The service account can see the folder itself, but it's reporting **zero files inside it**. "
                "Either the folder is genuinely empty, or the files are in a sub-folder (this app only reads "
                "the top level, not sub-folders) - move them up a level, or tell me and I can add recursive support."
            )
        elif not rag_server.documents:
            st.warning(
                f"Found {rag_server.total_files_found} file(s) in the folder, but none could be indexed. "
                "See why below:"
            )
            for skipped in rag_server.skipped_files:
                st.caption(f"- **{skipped['name']}**: {skipped['reason']}")
        else:
            for doc in rag_server.documents:
                st.markdown(f"- {doc['name']}")
            if rag_server.skipped_files:
                st.caption(f"({len(rag_server.skipped_files)} other file(s) skipped)")
                for skipped in rag_server.skipped_files:
                    st.caption(f"- **{skipped['name']}**: {skipped['reason']}")

    st.markdown("---")

    # Session State Initialization
    if "messages" not in st.session_state:
        st.session_state.messages = []

    # Display Chat History
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # Handle User Input
    if user_prompt := st.chat_input("Ask a question about the documents..."):
        if not groq_key:
            st.warning("Please provide a Groq API Key in your `.env` file or sidebar to proceed.")
            st.stop()

        st.session_state.messages.append({"role": "user", "content": user_prompt})
        with st.chat_message("user"):
            st.markdown(user_prompt)

        agent = RAGAgent(api_key=groq_key, rag_server=rag_server)

        with st.chat_message("assistant"):
            try:
                history_input = [
                    {"role": m["role"], "content": m["content"]}
                    for m in st.session_state.messages
                ]
                response_text = agent.run(history_input)
                st.markdown(response_text)
                st.session_state.messages.append({"role": "assistant", "content": response_text})
            except Exception as e:
                st.error(f"Error processing request with Groq: {str(e)}")


# ==============================================================================
# ENTRYPOINT
# ==============================================================================
if __name__ == "__main__":
    main()

# streamlit run app.py
