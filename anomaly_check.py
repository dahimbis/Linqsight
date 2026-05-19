"""
anomaly_check.py

Hourly job that texts the user if a metric spikes or drops.
Run as a cron job: python anomaly_check.py
On Render: set cron schedule to "0 * * * *" (every hour).
"""

import math
import os
from dotenv import load_dotenv
load_dotenv()
from db import run_query
from claude_client import write_anomaly_alert
from linq_client import send_text, get_or_create_chat

USER_NUMBER = os.environ["USER_PHONE_NUMBER"]
THRESHOLD_STD = 2.0   # alert if |z| >= 2


def get_rolling_stats(metric_sql_today: str, metric_sql_window: str):
    """
    Returns (today_value, window_avg, window_std).
    metric_sql_today  query returning a single scalar for today
    metric_sql_window query returning a list of daily values for the 14-day window
    """
    today_rows = run_query(metric_sql_today)
    today_val = list(today_rows[0].values())[0] if today_rows else 0
    today_val = today_val or 0

    window_rows = run_query(metric_sql_window)
    values = [list(r.values())[0] for r in window_rows if list(r.values())[0] is not None]
    if len(values) < 3:
        return today_val, None, None

    avg = sum(values) / len(values)
    variance = sum((v - avg) ** 2 for v in values) / len(values)
    std = math.sqrt(variance)
    return today_val, avg, std


METRICS = [
    {
        "name": "daily signups",
        "today_sql": "SELECT COUNT(*) FROM signups WHERE date = date('2026-05-19', '-1 day')",
        "window_sql": """
            SELECT COUNT(*) as n FROM signups
            WHERE date >= date('2026-05-19', '-15 days')
              AND date < date('2026-05-19', '-1 day')
            GROUP BY date ORDER BY date
        """,
    },
    {
        "name": "Google Ads CAC",
        "today_sql": """
            SELECT ROUND(SUM(s.spend) / MAX(1, COUNT(c.id)), 0)
            FROM ad_spend s
            LEFT JOIN signups sg ON sg.date = s.date AND sg.source = 'Google Ads'
            LEFT JOIN conversions c ON c.signup_id = sg.id
            WHERE s.channel = 'Google Ads'
              AND s.date = date('2026-05-19', '-1 day')
        """,
        "window_sql": """
            SELECT ROUND(SUM(s.spend) / MAX(1, COUNT(c.id)), 0) as cac
            FROM ad_spend s
            LEFT JOIN signups sg ON sg.date = s.date AND sg.source = 'Google Ads'
            LEFT JOIN conversions c ON c.signup_id = sg.id
            WHERE s.channel = 'Google Ads'
              AND s.date >= date('2026-05-19', '-15 days')
              AND s.date < date('2026-05-19', '-1 day')
            GROUP BY s.date ORDER BY s.date
        """,
    },
    {
        "name": "daily conversion rate (%)",
        "today_sql": """
            SELECT ROUND(100.0 * COUNT(c.id) / MAX(1, COUNT(s.id)), 2)
            FROM signups s
            LEFT JOIN conversions c ON c.signup_id = s.id
            WHERE s.date = date('2026-05-19', '-1 day')
        """,
        "window_sql": """
            SELECT ROUND(100.0 * COUNT(c.id) / MAX(1, COUNT(s.id)), 2) as rate
            FROM signups s
            LEFT JOIN conversions c ON c.signup_id = s.id
            WHERE s.date >= date('2026-05-19', '-15 days')
              AND s.date < date('2026-05-19', '-1 day')
            GROUP BY s.date ORDER BY s.date
        """,
    },
]


def run():
    chat_id = get_or_create_chat(USER_NUMBER)
    alerts_sent = 0

    for m in METRICS:
        today_val, avg, std = get_rolling_stats(m["today_sql"], m["window_sql"])
        if avg is None or std is None or std == 0:
            continue

        z = (today_val - avg) / std
        if abs(z) >= THRESHOLD_STD:
            direction = "above" if z > 0 else "below"
            alert = write_anomaly_alert(
                metric=m["name"],
                value=today_val,
                avg=avg,
                std=std,
                direction=direction,
            )
            send_text(alert, to=USER_NUMBER, chat_id=chat_id)
            alerts_sent += 1
            print(f"Alert sent for {m['name']}: {today_val:.1f} (z={z:.2f})")

    if alerts_sent == 0:
        print("No anomalies detected.")


if __name__ == "__main__":
    run()
