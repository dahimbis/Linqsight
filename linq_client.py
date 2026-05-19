"""
linq_client.py

Thin wrapper around the Linq Partner API v3.
Handles sending messages, typing indicators, and chat creation/lookup.
"""

import os
import httpx
from typing import Optional

LINQ_BASE = "https://api.linqapp.com/api/partner/v3"
LINQ_API_KEY = os.environ["LINQ_API_KEY"]
LINQ_FROM_NUMBER = os.environ["LINQ_FROM_NUMBER"]   # your registered Linq number
USER_NUMBER = os.environ["USER_PHONE_NUMBER"]        # the analyst's personal number

_headers = {
    "Authorization": f"Bearer {LINQ_API_KEY}",
    "Content-Type": "application/json",
}


def _client() -> httpx.Client:
    return httpx.Client(headers=_headers, timeout=15)


# ── chat management ────────────────────────────────────────────────────────────

def get_or_create_chat(to: str = USER_NUMBER) -> str:
    """
    Return an existing chat ID for `to`, or create one.
    We cache the chat_id in a tiny local file to avoid re-creating on every call.
    """
    cache_file = f".chat_id_{to.replace('+', '')}"
    if os.path.exists(cache_file):
        with open(cache_file) as f:
            return f.read().strip()

    # Create a new chat with a silent first message (we'll send the real one next)
    with _client() as client:
        resp = client.post(
            f"{LINQ_BASE}/chats",
            json={
                "from": LINQ_FROM_NUMBER,
                "to": [to],
                "message": {
                    "parts": [{"type": "text", "value": "👋"}],
                    "preferred_service": "iMessage",
                },
            },
        )
        resp.raise_for_status()
        chat_id = resp.json()["chat_id"]

    with open(cache_file, "w") as f:
        f.write(chat_id)
    return chat_id


# ── messaging ──────────────────────────────────────────────────────────────────

def send_text(text: str, to: str = USER_NUMBER, chat_id: Optional[str] = None) -> dict:
    """Send a plain-text iMessage. Returns the API response dict."""
    if chat_id is None:
        chat_id = get_or_create_chat(to)
    with _client() as client:
        resp = client.post(
            f"{LINQ_BASE}/chats/{chat_id}/messages",
            json={
                "message": {
                    "parts": [{"type": "text", "value": text}],
                    "preferred_service": "iMessage",
                }
            },
        )
        resp.raise_for_status()
        return resp.json()


def send_image(image_url: str, caption: Optional[str] = None,
               to: str = USER_NUMBER, chat_id: Optional[str] = None) -> dict:
    """Send an image (with optional caption text) via a public URL."""
    if chat_id is None:
        chat_id = get_or_create_chat(to)
    parts = []
    if caption:
        parts.append({"type": "text", "value": caption})
    parts.append({"type": "media", "url": image_url})
    with _client() as client:
        resp = client.post(
            f"{LINQ_BASE}/chats/{chat_id}/messages",
            json={"message": {"parts": parts, "preferred_service": "iMessage"}},
        )
        resp.raise_for_status()
        return resp.json()


# ── typing indicators ──────────────────────────────────────────────────────────

def start_typing(chat_id: str) -> None:
    with _client() as client:
        client.post(f"{LINQ_BASE}/chats/{chat_id}/typing")


def stop_typing(chat_id: str) -> None:
    with _client() as client:
        client.delete(f"{LINQ_BASE}/chats/{chat_id}/typing")
