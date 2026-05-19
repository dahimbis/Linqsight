"""
webhook.py

FastAPI server.
POST /webhook  receives Linq message.received events
GET  /health   Render health check
"""

import os
import hmac
import hashlib
import time
import asyncio
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

load_dotenv()

from db import save_message, get_history, save_memory, clear_history
from claude_client import answer_question, extract_memory, classify_intent, handle_chat
from linq_client import send_text, start_typing, stop_typing, get_or_create_chat

app = FastAPI(title="Linqsight")

WEBHOOK_SECRET = os.environ.get("LINQ_WEBHOOK_SECRET", "")
USER_NUMBER = os.environ["USER_PHONE_NUMBER"]


def verify_signature(secret: str, timestamp: str, body: bytes, sig: str) -> bool:
    """HMAC-SHA256 over '{timestamp}.{body}' per Linq docs."""
    if not secret:
        return True  # skip in dev if secret not set
    message = f"{timestamp}.{body.decode('utf-8')}"
    expected = hmac.new(
        secret.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, sig)


@app.get("/")
async def root():
    return {"name": "Linqsight", "status": "ok"}


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/webhook")
async def webhook(request: Request, background_tasks: BackgroundTasks):
    body = await request.body()

    # Signature verification
    if WEBHOOK_SECRET:
        sig = request.headers.get("X-Webhook-Signature", "")
        ts = request.headers.get("X-Webhook-Timestamp", "")
        if not verify_signature(WEBHOOK_SECRET, ts, body, sig):
            raise HTTPException(status_code=401, detail="Invalid signature")

    payload = await request.json()
    event_type = payload.get("event_type")

    # Only handle inbound messages
    if event_type != "message.received":
        return JSONResponse({"ok": True})

    data = payload.get("data", {})
    direction = data.get("direction", "")
    if direction != "inbound":
        return JSONResponse({"ok": True})

    # Extract sender and text
    sender_handle = data.get("sender_handle", {})
    sender = sender_handle.get("handle", "")
    parts = data.get("parts", [])
    text_parts = [p["value"] for p in parts if p.get("type") == "text"]
    user_text = " ".join(text_parts).strip()

    if not user_text or not sender:
        return JSONResponse({"ok": True})

    # Only respond to the configured user
    if sender != USER_NUMBER:
        return JSONResponse({"ok": True})

    # Process in background so we return 200 immediately to Linq
    chat_id = data.get("chat", {}).get("id")
    background_tasks.add_task(handle_message, sender, user_text, chat_id)
    return JSONResponse({"ok": True})


async def handle_message(sender: str, user_text: str, chat_id: str | None):
    """Process the message, call Claude, send reply."""
    # Save user message
    save_message(sender, "user", user_text)

    # Get or resolve chat_id
    if not chat_id:
        chat_id = get_or_create_chat(sender)

    # Show typing indicator while we think
    try:
        start_typing(chat_id)
    except Exception:
        pass

    try:
        history = get_history(sender, limit=8)
        intent = classify_intent(user_text)

        # Reset command clears conversation history
        if user_text.strip().lower() in ("reset", "clear", "start over", "new conversation"):
            clear_history(sender)
            reply = "Fresh start. What do you want to dig into?"
        elif intent == "memory":
            mem = extract_memory(user_text)
            if mem:
                save_memory(mem["key"], mem["value"])
                reply = f"Got it, I'll remember that {mem['key'].replace('_', ' ')} is {mem['value']}."
            else:
                reply = handle_chat(user_text, history)
        elif intent == "chat":
            reply = handle_chat(user_text, history)
        else:
            reply = answer_question(user_text, history)
        save_message(sender, "assistant", reply)
        send_text(reply, to=sender, chat_id=chat_id)

    except Exception as e:
        error_reply = "Something went sideways on my end. Try again in a sec?"
        send_text(error_reply, to=sender, chat_id=chat_id)
        raise e
    finally:
        try:
            stop_typing(chat_id)
        except Exception:
            pass
