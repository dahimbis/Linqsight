"""
daily_brief.py

Sends the morning brief at 8am.
Run as a cron job: python daily_brief.py
On Render: set cron schedule to "0 8 * * *" (UTC, adjust for your timezone).
"""

import json
import os
from dotenv import load_dotenv
load_dotenv()
from db import run_query
from claude_client import write_daily_brief
from linq_client import send_text, get_or_create_chat
import os

USER_NUMBER = os.environ["USER_PHONE_NUMBER"]

YESTERDAY = "date('2026-05-19', '-1 day')"
WEEK_AGO  = "date('2026-05-19', '-8 days')"
MONTH_AGO = "date('2026-05-19', '-31 days')"


def fetch_metrics() -> dict:
    """Pull yesterday's key metrics plus WoW and MoM comparisons."""

    def scalar(sql):
        rows = run_query(sql)
        if rows:
            v = list(rows[0].values())[0]
            return v if v is not None else 0
        return 0

    # ── signups ────────────────────────────────────────────────────────────────
    signups_yday = scalar(
        f"SELECT COUNT(*) FROM signups WHERE date = {YESTERDAY}"
    )
    signups_wow = scalar(
        f"SELECT COUNT(*) FROM signups WHERE date = {WEEK_AGO}"
    )
    signups_mom = scalar(
        f"SELECT COUNT(*) FROM signups WHERE date = {MONTH_AGO}"
    )

    # ── source breakdown yesterday ─────────────────────────────────────────────
    source_rows = run_query(
        f"SELECT source, COUNT(*) as n FROM signups WHERE date = {YESTERDAY} "
        "GROUP BY source ORDER BY n DESC"
    )

    # ── activation rate (last 7 days) ──────────────────────────────────────────
    act_rate_7d = scalar("""
        SELECT ROUND(100.0 * COUNT(a.id) / COUNT(s.id), 1)
        FROM signups s
        LEFT JOIN activations a ON a.signup_id = s.id
        WHERE s.date >= date('2026-05-19', '-7 days')
    """)
    act_rate_prev_7d = scalar("""
        SELECT ROUND(100.0 * COUNT(a.id) / COUNT(s.id), 1)
        FROM signups s
        LEFT JOIN activations a ON a.signup_id = s.id
        WHERE s.date >= date('2026-05-19', '-14 days')
          AND s.date < date('2026-05-19', '-7 days')
    """)

    # ── conversion rate (last 7 days) ──────────────────────────────────────────
    conv_rate_7d = scalar("""
        SELECT ROUND(100.0 * COUNT(c.id) / COUNT(s.id), 1)
        FROM signups s
        LEFT JOIN conversions c ON c.signup_id = s.id
        WHERE s.date >= date('2026-05-19', '-7 days')
    """)

    # ── new MRR yesterday ─────────────────────────────────────────────────────
    new_mrr_yday = scalar(
        f"SELECT ROUND(SUM(mrr), 0) FROM conversions "
        f"WHERE date(converted_at) = {YESTERDAY}"
    )
    new_mrr_wow = scalar(
        f"SELECT ROUND(SUM(mrr), 0) FROM conversions "
        f"WHERE date(converted_at) = {WEEK_AGO}"
    )

    # ── Google Ads CAC (last 7 days vs prior 7) ────────────────────────────────
    google_cac_7d = scalar("""
        SELECT ROUND(SUM(s.spend) / MAX(1, COUNT(c.id)), 0)
        FROM ad_spend s
        LEFT JOIN signups sg ON sg.date = s.date AND sg.source = 'Google Ads'
        LEFT JOIN conversions c ON c.signup_id = sg.id
        WHERE s.channel = 'Google Ads'
          AND s.date >= date('2026-05-19', '-7 days')
    """)
    google_cac_prev = scalar("""
        SELECT ROUND(SUM(s.spend) / MAX(1, COUNT(c.id)), 0)
        FROM ad_spend s
        LEFT JOIN signups sg ON sg.date = s.date AND sg.source = 'Google Ads'
        LEFT JOIN conversions c ON c.signup_id = sg.id
        WHERE s.channel = 'Google Ads'
          AND s.date >= date('2026-05-19', '-14 days')
          AND s.date < date('2026-05-19', '-7 days')
    """)

    # ── LinkedIn activation rate (last 7 days) ─────────────────────────────────
    li_act_rate = scalar("""
        SELECT ROUND(100.0 * COUNT(a.id) / MAX(1, COUNT(s.id)), 1)
        FROM signups s
        LEFT JOIN activations a ON a.signup_id = s.id
        WHERE s.source = 'LinkedIn'
          AND s.date >= date('2026-05-19', '-7 days')
    """)

    return {
        "date": "2026-05-18",  # yesterday
        "signups": {
            "yesterday": signups_yday,
            "same_day_last_week": signups_wow,
            "same_day_last_month": signups_mom,
            "wow_pct": _pct_change(signups_yday, signups_wow),
        },
        "top_sources_yesterday": source_rows,
        "activation_rate_pct": {
            "last_7_days": act_rate_7d,
            "prior_7_days": act_rate_prev_7d,
        },
        "conversion_rate_pct_last_7d": conv_rate_7d,
        "new_mrr": {
            "yesterday": new_mrr_yday,
            "same_day_last_week": new_mrr_wow,
            "wow_pct": _pct_change(new_mrr_yday, new_mrr_wow),
        },
        "google_ads_cac": {
            "last_7_days": google_cac_7d,
            "prior_7_days": google_cac_prev,
            "wow_pct": _pct_change(google_cac_7d, google_cac_prev),
        },
        "linkedin_activation_rate_pct_last_7d": li_act_rate,
    }


def _pct_change(current, prior) -> float | None:
    if not prior:
        return None
    return round((current - prior) / prior * 100, 1)


def run():
    metrics = fetch_metrics()
    brief = write_daily_brief(metrics)
    chat_id = get_or_create_chat(USER_NUMBER)
    send_text(brief, to=USER_NUMBER, chat_id=chat_id)
    print(f"Brief sent:\n{brief}")


if __name__ == "__main__":
    run()
