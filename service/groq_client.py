"""
groq_client.py
----------------
Shared helper for talking to Groq's AI API (https://groq.com). Every feature
that calls Groq — the dashboard chatbot, the daily summary email — creates
its client through here, so the "is the API key set?" check only lives in
one place.
"""

import os

from dotenv import load_dotenv

load_dotenv()

# The model used for every Groq call in this app. "openai/gpt-oss-120b" is
# an open-weight model Groq hosts and runs very fast.
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")


class GroqNotConfiguredError(Exception):
    """Raised when GROQ_API_KEY is missing, so callers can return a clean error."""


def get_client():
    """Return a ready-to-use Groq client, or raise GroqNotConfiguredError."""
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise GroqNotConfiguredError("GROQ_API_KEY is not set.")
    from groq import Groq  # imported lazily so the package is only needed if used

    return Groq(api_key=api_key)
