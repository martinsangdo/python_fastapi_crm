"""
chatbot_schemas.py
--------------------
Pydantic schemas for the dashboard's "ask about the data" chatbot.
"""

from typing import List, Literal

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    """One turn of the conversation, sent back by the browser as history."""

    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    """Body for POST /api/dashboard/chat."""

    message: str = Field(min_length=1, max_length=2000)
    # The last few turns, so the AI can follow up on what was just discussed.
    # The browser keeps this; the server itself stores no conversation state.
    history: List[ChatMessage] = []


class ChatResponse(BaseModel):
    """The AI's reply."""

    reply: str
