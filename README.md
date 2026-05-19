# Linqsight

> A growth analyst that lives on iMessage.

Linqsight texts your growth team the way a smart colleague would, not a dashboard. It sends a morning brief every day, answers follow-up questions in plain English, and fires unprompted alerts when something unusual happens in the data.

Built on the [Linq API](https://linqapp.com), Claude (Anthropic), FastAPI, and SQLite. Deployable to Render in under 5 minutes.

---

## What it does

**1. Daily morning brief (8am)**
A 3–4 sentence iMessage summarising yesterday's key metrics vs the prior week. Specific numbers, colleague voice, ends with a question.

**2. Conversational follow-up**
Text the bot any question ("why did signups drop?" or "break down CAC by channel") and it writes a SQL query, runs it, and replies in plain English. Remembers the last 8 messages so "why?" works without repeating yourself.

**3. Anomaly alerts**
An hourly job checks signups, Google Ads CAC, and conversion rate against their 14-day rolling average. If anything is ≥ 2 standard deviations off, it texts you unprompted.

**Bonus: memory**
Text the bot a fact like "our CAC target is $40" and it stores it and applies it in future briefs and replies.

---

## Quickstart (5 minutes)

### 1. Clone and install

```bash
git clone https://github.com/yourname/linqsight.git
cd linqsight
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Set environment variables

```bash
cp .env.example .env
# Edit .env with your keys
```

You need:
- A [Linq Partner API key](https://linqapp.com) and a registered phone number
- An [Anthropic API key](https://console.anthropic.com)
- Your personal phone number (the analyst's number)

### 3. Generate the database

```bash
python generate_data.py
```

This creates `linqsight.db` with 180 days of synthetic SaaS data. Reproducible, same data every time.

### 4. Run locally

```bash
uvicorn webhook:app --reload
```

Expose it with [ngrok](https://ngrok.com) for local testing:

```bash
ngrok http 8000
```

Point your Linq webhook subscription at `https://your-ngrok-url/webhook` and subscribe to `message.received`.

### 5. Test the daily brief

```bash
python daily_brief.py
```

### 6. Deploy to Render

Push to GitHub, connect the repo in Render, and use `render.yaml`. Set the five environment variables in the Render dashboard. The build step runs `generate_data.py` automatically.

---

## Project structure

```
linqsight/
├── generate_data.py   # Creates linqsight.db from scratch (run once)
├── webhook.py         # FastAPI server, receives Linq webhooks
├── daily_brief.py     # Morning brief cron job
├── anomaly_check.py   # Hourly anomaly detection cron job
├── claude_client.py   # All Claude interactions (SQL gen + summarisation)
├── linq_client.py     # Linq API wrapper (send, typing indicators)
├── db.py              # SQLite helpers + schema description
├── requirements.txt
├── render.yaml        # Render deployment config
└── .env.example
```

Total: ~450 lines of Python. Read it in 15 minutes.

---

## The data

`generate_data.py` produces a realistic 180-day SaaS dataset with these patterns baked in:

| Pattern | Detail |
|---|---|
| Weekend dip | ~30% fewer signups on Sat/Sun |
| LinkedIn paradox | Highest volume source, lowest activation rate (~31%) |
| Google Ads CAC spike | +22% in the last 7 days, new creative underperforms |
| Reddit viral day | One day in the last 30 with 3–4× normal signups |
| Growth trend | +1.5%/week overall |
| Winning experiment | "Onboarding v2" ran in month 3, variant B clearly won |

---

## Plugging into real Linq data

The synthetic database mirrors the shape of what Linq already tracks internally. Swapping it out is a one-file change (`db.py` + `generate_data.py`):

| Synthetic table | Real Linq equivalent |
|---|---|
| `signups` | New account registrations, attributed by UTM source |
| `activations` | First meaningful action (first message sent, first integration connected) |
| `conversions` | Plan upgrades, with MRR from Stripe |
| `ad_spend` | Google Ads / LinkedIn spend pulled via their APIs or a warehouse |
| `experiments` | A/B test log from LaunchDarkly, Statsig, or a homegrown table |

The Claude prompts and the anomaly logic are data-agnostic. They work off the schema description in `db.py`. Update that description and the queries in `daily_brief.py` and `anomaly_check.py`, and Linqsight is running on real data.

For a production deployment you'd also want:
- A read replica or a warehouse (BigQuery, Snowflake) instead of SQLite
- Proper auth if more than one person is texting the bot
- A secrets manager instead of environment variables

---

## Design choices

**Why two-step Claude calls (SQL then summarise)?**
Separating "what does the data say" from "how do I say it" keeps each prompt focused. The SQL prompt is strict and technical; the summarisation prompt is purely about voice. Mixing them produces worse output on both dimensions.

**Why SQLite?**
Zero infrastructure, ships with Python, and the dataset fits in memory. For a portfolio piece it's the right call. The query interface is identical to Postgres, so swapping the driver is a one-line change.

**Why store conversation history in SQLite?**
Keeps the architecture simple and the history durable across restarts. For a single user, a table with 8-message lookback is plenty.

**Why not stream Claude's response?**
The typing indicator covers the latency. Streaming adds complexity for a text message that's 2 sentences long.

---

## Voice and tone

The system prompts are the most important part of this project. The rules:

- Lead with what changed, not with context
- Specific numbers always ("287 signups, up 12%" not "signups grew")
- 3–4 sentences for briefs, 1–2 for replies
- End with a question that invites a follow-up
- No bullet points, no headers, no emoji unless the user used one first
- No corporate phrases

This is the same insight behind Linq Blue: a text from a person feels different from a notification from a system, even when the information is identical.

---

## License

MIT
