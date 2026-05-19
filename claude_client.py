"""
claude_client.py

All Claude interactions in one place.

Two-step pattern for conversational queries:
  1. SQL generation  →  run query  →  2. Summarise results

System prompts are tuned for the "colleague texting" voice.
"""

import os
import re
import json
from anthropic import Anthropic
from db import SCHEMA_DESCRIPTION, run_query, get_memories

MODEL = "claude-haiku-4-5"
client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

# ── system prompts ─────────────────────────────────────────────────────────────

SQL_SYSTEM = f"""You are a SQL expert working with a SaaS growth database.
Given a user question, write a single SQLite SELECT query that answers it.

{SCHEMA_DESCRIPTION}

Rules:
- Return ONLY the raw SQL query. No markdown, no explanation, no backticks.
- Use date('now') carefully, the dataset is pinned to 2026-05-19.
- For "yesterday" use date('2026-05-19', '-1 day').
- For "last 7 days" use date >= date('2026-05-19', '-7 days').
- For "last 14 days" use date >= date('2026-05-19', '-14 days').
- For "last 30 days" use date >= date('2026-05-19', '-30 days').
- Activation rate = activations / signups for the same cohort.
- CAC = total ad_spend / conversions for the same channel/period.
- If the question is unanswerable from the schema, return: SELECT 'no_data' AS result;
"""

BRIEF_SYSTEM = """You are Linqsight, a growth analyst texting your colleague.
Your job: turn raw query results into a short, punchy iMessage.

Voice rules (non-negotiable):
- 3-4 sentences max. Never more.
- Lead with what changed or what matters, not with context.
- Use specific numbers. "287 signups, up 12%" not "signups grew."
- End with one question that invites a follow-up.
- No bullet points. No headers. No emoji unless the user used one first.
- No corporate phrases. Sound like a smart friend, not a dashboard.
- Write in plain prose, like a text message.
"""

ANOMALY_SYSTEM = """You are Linqsight, a growth analyst texting your colleague about an anomaly.
Keep it to 2 sentences: what happened and why it might matter.
Be specific with numbers. No fluff. End with a question."""

MEMORY_SYSTEM = """The user is storing a fact for you to remember.
Extract the key and value from their message and return JSON like:
{"key": "cac_target", "value": "$40"}
Keys should be snake_case. Values should be the exact fact stated.
Return ONLY the JSON object, nothing else."""


def _memories_context() -> str:
    mems = get_memories()
    if not mems:
        return ""
    lines = "\n".join(f"- {m['key']}: {m['value']}" for m in mems)
    return f"\n\nUser-defined context (apply these in your analysis):\n{lines}"


def generate_sql(question: str, history: list[dict]) -> str:
    """Ask Claude to write a SQL query for the user's question."""
    messages = history + [{"role": "user", "content": question}]
    resp = client.messages.create(
        model=MODEL,
        max_tokens=512,
        system=SQL_SYSTEM + _memories_context(),
        messages=messages,
    )
    return resp.content[0].text.strip()


def summarise_results(question: str, sql: str, results: list[dict],
                      history: list[dict]) -> str:
    """Turn query results into a colleague-voice reply."""
    results_str = json.dumps(results[:50], indent=2)  # cap at 50 rows for context
    prompt = (
        f"The user asked: {question}\n\n"
        f"SQL run: {sql}\n\n"
        f"Results:\n{results_str}\n\n"
        "Reply as Linqsight, colleague voice, specific numbers, 1-2 sentences, "
        "end with a follow-up question."
    )
    messages = history + [{"role": "user", "content": prompt}]
    resp = client.messages.create(
        model=MODEL,
        max_tokens=300,
        system=BRIEF_SYSTEM + _memories_context(),
        messages=messages,
    )
    return resp.content[0].text.strip()


def answer_question(question: str, history: list[dict]) -> str:
    """Full two-step: SQL → run → summarise. Returns the final reply text."""
    sql = generate_sql(question, history)

    # Safety: only allow SELECT
    clean = sql.strip().upper()
    if not clean.startswith("SELECT"):
        return "I can only read data, not modify it. Try rephrasing as a question about the numbers."

    try:
        results = run_query(sql)
    except Exception as e:
        return f"Ran into a data issue: {e}. Try rephrasing?"

    if not results or results == [{"result": "no_data"}]:
        return "I don't have data to answer that one. Try asking about signups, conversions, ad spend, or experiments."

    return summarise_results(question, sql, results, history)


def write_daily_brief(metrics: dict) -> str:
    """Generate the morning brief from a pre-built metrics dict."""
    prompt = (
        "Write a morning brief iMessage for the growth team. "
        "Here are yesterday's metrics vs prior week and prior month:\n\n"
        + json.dumps(metrics, indent=2)
        + "\n\nRemember: 3-4 sentences, lead with what changed, specific numbers, "
        "end with a question. Colleague voice."
    )
    resp = client.messages.create(
        model=MODEL,
        max_tokens=300,
        system=BRIEF_SYSTEM + _memories_context(),
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.content[0].text.strip()


def write_anomaly_alert(metric: str, value: float, avg: float,
                        std: float, direction: str) -> str:
    """Generate a short anomaly alert text."""
    z = abs(value - avg) / std if std > 0 else 0
    prompt = (
        f"Anomaly detected: {metric} is {value:.1f} today, "
        f"vs 14-day average of {avg:.1f} (std dev {std:.1f}). "
        f"That's {z:.1f} standard deviations {direction}. "
        "Write a 2-sentence alert. Specific numbers. End with a question."
    )
    resp = client.messages.create(
        model=MODEL,
        max_tokens=150,
        system=ANOMALY_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.content[0].text.strip()


def extract_memory(user_message: str) -> dict | None:
    """
    If the user is storing a fact (e.g. "our CAC target is $40"),
    return {"key": ..., "value": ...}. Otherwise return None.
    """
    resp = client.messages.create(
        model=MODEL,
        max_tokens=100,
        system=MEMORY_SYSTEM,
        messages=[{"role": "user", "content": user_message}],
    )
    text = resp.content[0].text.strip()
    try:
        data = json.loads(text)
        if "key" in data and "value" in data:
            return data
    except Exception:
        pass
    return None


INTENT_SYSTEM = """You classify a message from a growth analyst into one of three categories.
Reply with exactly one word, nothing else:

- data    (asking about metrics, signups, revenue, CAC, activation, experiments, trends, dashboards, reports)
- memory  (storing a fact like "our CAC target is $40" or "remember that...")
- chat    (greeting, small talk, off-topic, personal questions, anything not data-related)

Examples:
"hey" -> chat
"how did we do yesterday" -> data
"what's our conversion rate" -> data
"our CAC target is $40" -> memory
"how is Katie" -> chat
"any dashboards" -> chat
"break that down by channel" -> data
"thanks" -> chat
"""

CHAT_SYSTEM = """You are Linqsight, a growth analyst assistant on iMessage.
The user said something that isn't a data question. Reply naturally in 1 sentence.
If it's a greeting, say hi back and mention you're ready to dig into growth data.
If it's off-topic or personal, politely note you're focused on growth metrics.
No bullet points. No emoji unless they used one. Sound like a real person."""


def classify_intent(text: str) -> str:
    """Returns 'data', 'memory', or 'chat'."""
    resp = client.messages.create(
        model=MODEL,
        max_tokens=5,
        system=INTENT_SYSTEM,
        messages=[{"role": "user", "content": text}],
    )
    result = resp.content[0].text.strip().lower()
    if result in ("data", "memory", "chat"):
        return result
    return "data"  # default to data if unclear


def handle_chat(text: str, history: list[dict]) -> str:
    """Reply naturally to greetings and off-topic messages."""
    messages = history + [{"role": "user", "content": text}]
    resp = client.messages.create(
        model=MODEL,
        max_tokens=100,
        system=CHAT_SYSTEM,
        messages=messages,
    )
    return resp.content[0].text.strip()
