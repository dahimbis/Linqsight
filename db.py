"""
db.py

SQLite helpers shared across all modules.
"""

import sqlite3
import os
from contextlib import contextmanager
from typing import Generator

DB_PATH = os.environ.get("DB_PATH", "linqsight.db")

SCHEMA = """
SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;
"""

# Human-readable schema description passed to Claude as context
SCHEMA_DESCRIPTION = """
SQLite database: linqsight.db  (180 days of synthetic SaaS growth data, pinned to 2026-05-19)

Tables:
  signups(id, date TEXT, source TEXT, email_domain TEXT, company_size TEXT)
    source values: 'Google Ads', 'LinkedIn', 'Reddit', 'organic', 'referral'
    company_size values: '1-10', '11-50', '51-200', '201-1000', '1000+'

  activations(id, signup_id INTEGER, activated_at TEXT, activation_event TEXT)
    activation_event values: 'connected_integration', 'sent_first_message',
                              'invited_teammate', 'completed_onboarding'

  conversions(id, signup_id INTEGER, converted_at TEXT, plan TEXT, mrr REAL)
    plan values: 'starter'($49), 'growth'($149), 'pro'($399), 'enterprise'($999)

  ad_spend(id, date TEXT, channel TEXT, spend REAL, impressions INTEGER, clicks INTEGER)
    channel values: 'Google Ads', 'LinkedIn'

  experiments(id, start_date TEXT, end_date TEXT, name TEXT,
              variant_a TEXT, variant_b TEXT, winner TEXT)
    Notable: 'Onboarding v2' ran in month 3, winner='variant_b' (clear win)

  conversations(id, sender TEXT, role TEXT, content TEXT, created_at TEXT)
  memories(id, key TEXT, value TEXT, created_at TEXT)

Key patterns baked in:
  - Weekend signups ~30% lower (Sat/Sun)
  - LinkedIn highest volume but lowest activation rate (~31%)
  - Google Ads CAC spiked ~22% in the last 7 days (new creative underperforms)
  - One Reddit viral day in the last 30 days (3-4x normal signups)
  - Overall signup trend: +1.5%/week
  - Onboarding v2 experiment clearly won in month 3

Today's date: 2026-05-19
"""


@contextmanager
def get_conn() -> Generator[sqlite3.Connection, None, None]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def run_query(sql: str) -> list[dict]:
    """Execute a SELECT and return rows as list of dicts. Raises on error."""
    with get_conn() as conn:
        cur = conn.execute(sql)
        return [dict(row) for row in cur.fetchall()]


def save_message(sender: str, role: str, content: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO conversations (sender, role, content) VALUES (?, ?, ?)",
            (sender, role, content),
        )
        conn.commit()


def get_history(sender: str, limit: int = 8) -> list[dict]:
    """Return the last `limit` messages for a sender, oldest first."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT role, content FROM conversations "
            "WHERE sender = ? ORDER BY id DESC LIMIT ?",
            (sender, limit),
        ).fetchall()
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


def save_memory(key: str, value: str) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM memories WHERE key = ?", (key,))
        conn.execute("INSERT INTO memories (key, value) VALUES (?, ?)", (key, value))
        conn.commit()


def get_memories() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute("SELECT key, value FROM memories ORDER BY id").fetchall()
    return [dict(r) for r in rows]
