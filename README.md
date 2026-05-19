# Linqsight

> A growth analyst that lives on iMessage.

Linqsight texts your growth team the way a smart colleague would, not a dashboard. It sends a morning brief every day, answers follow-up questions in plain English, and fires unprompted alerts when something unusual happens in the data.

Built on the [Linq API](https://linqapp.com), Claude (Anthropic), FastAPI, and SQLite. Deployed on Render.

---

## What it does

**1. Daily morning brief (8am)**
A 3-4 sentence iMessage summarising yesterday's key metrics vs the prior week. Specific numbers, colleague voice, ends with a question.

**2. Conversational follow-up**
Text the bot any question ("why did signups drop?" or "break down CAC by channel") and it writes a SQL query, runs it, and replies in plain English. Remembers the last 8 messages so "why?" works without repeating yourself.

**3. Anomaly alerts**
An hourly job checks signups, Google Ads CAC, and conversion rate against their 14-day rolling average. If anything is 2 or more standard deviations off, it texts you unprompted.

**4. Memory**
Text the bot a fact like "our CAC target is $40" and it stores it and applies it in future briefs and replies.

**5. Reset**
Text `reset`, `clear`, or `start over` to wipe the conversation history and start fresh.

---

## How it works

Every inbound text goes through a three-step pipeline:

1. **Intent classification** — Claude decides if the message is a data question, a fact to remember, or casual chat. Greetings get a natural reply. Off-topic questions get a polite redirect. Data questions go to step 2.
2. **SQL generation** — Claude writes a SQLite query against the schema. Only SELECT queries are allowed.
3. **Summarisation** — Claude turns the raw results into a 1-2 sentence colleague-voice reply and sends it back via the Linq API.

The daily brief and anomaly checks run as separate cron jobs and text you unprompted.

---

## Quickstart (5 minutes)

### 1. Clone and install

```bash
git clone https://github.com/yourname/linqsight.git
cd linqsight
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Mac/Linux
pip install -r requirements.txt
```

### 2. Set environment variables

```bash
cp .env.example .env
# Fill in your keys
```

You need:
- A Linq Partner API key and registered phone number from [linqapp.com](https://linqapp.com)
- An Anthropic API key from [console.anthropic.com](https://console.anthropic.com)
- Your personal phone number (the only number that can text the bot)

### 3. Generate the database

```bash
python generate_data.py
```

Creates `linqsight.db` with 180 days of synthetic SaaS data. Reproducible, same data every time.

### 4. Run locally

```bash
uvicorn webhook:app --reload
```

Use [ngrok](https://ngrok.com) to expose it publicly, then register your webhook with Linq pointing at `https://your-ngrok-url/webhook?version=2026-02-03`.

### 5. Test manually

```bash
python daily_brief.py     # sends the morning brief to your phone right now
python anomaly_check.py   # runs the anomaly check right now
```

### 6. Deploy to Render

1. Push to GitHub
2. Connect the repo on [render.com](https://render.com), create a Web Service
3. Set the build command: `pip install -r requirements.txt`
4. Set the start command: `python generate_data.py; uvicorn webhook:app --host 0.0.0.0 --port $PORT`
5. Add the five environment variables in the Render dashboard
6. Register your Linq webhook pointing at `https://your-app.onrender.com/webhook?version=2026-02-03`
7. Copy the `signing_secret` from the registration response into `LINQ_WEBHOOK_SECRET`

---

## Project structure

```
linqsight/
├── generate_data.py   # Creates linqsight.db from scratch
├── webhook.py         # FastAPI server, receives Linq webhooks
├── daily_brief.py     # Morning brief cron job
├── anomaly_check.py   # Hourly anomaly detection cron job
├── claude_client.py   # All Claude interactions (intent, SQL, summarisation, memory)
├── linq_client.py     # Linq API wrapper (send messages, typing indicators)
├── db.py              # SQLite helpers, schema description, table init
├── start.sh           # Startup script for Render
├── requirements.txt
├── render.yaml        # Render deployment config
└── .env.example
```

---

## Environment variables

| Variable | Description |
|---|---|
| `LINQ_API_KEY` | Your Linq Partner API bearer token |
| `LINQ_FROM_NUMBER` | Your registered Linq phone number (E.164 format) |
| `LINQ_WEBHOOK_SECRET` | Signing secret from your webhook subscription |
| `USER_PHONE_NUMBER` | Your personal number that texts the bot (E.164 format) |
| `ANTHROPIC_API_KEY` | Your Anthropic API key |

---

## The data

`generate_data.py` produces a realistic 180-day SaaS dataset with these patterns baked in:

| Pattern | Detail |
|---|---|
| Weekend dip | ~30% fewer signups on Sat/Sun |
| LinkedIn paradox | Highest volume source, lowest activation rate (~31%) |
| Google Ads CAC spike | +22% in the last 7 days, new creative underperforms |
| Reddit viral day | One day in the last 30 with 3-4x normal signups |
| Growth trend | +1.5%/week overall |
| Winning experiment | "Onboarding v2" ran in month 3, variant B clearly won |

---

## Plugging into real Linq data

The synthetic database mirrors the shape of what Linq already tracks internally. Swapping it out is a one-file change in `db.py` and `generate_data.py`:

| Synthetic table | Real Linq equivalent |
|---|---|
| `signups` | New account registrations, attributed by UTM source |
| `activations` | First meaningful action (first message sent, first integration connected) |
| `conversions` | Plan upgrades, with MRR from Stripe |
| `ad_spend` | Google Ads / LinkedIn spend pulled via their APIs or a warehouse |
| `experiments` | A/B test log from LaunchDarkly, Statsig, or a homegrown table |

The Claude prompts and anomaly logic are data-agnostic. They work off the schema description in `db.py`. Update that description and the queries in `daily_brief.py` and `anomaly_check.py`, and Linqsight is running on real data the same day.

For a production deployment you would also want:
- A read replica or warehouse (BigQuery, Snowflake) instead of SQLite
- Auth if more than one person is texting the bot
- A secrets manager instead of environment variables

---

## Design choices

**Intent classification before SQL generation**
Not every message is a data question. Routing greetings and off-topic messages through a separate Claude call first means the bot responds naturally to "hey" instead of trying to write SQL for it. Three intents: data, memory, chat.

**Two-step Claude calls for data questions**
Separating "what does the data say" from "how do I say it" keeps each prompt focused. The SQL prompt is strict and technical. The summarisation prompt is purely about voice. Mixing them produces worse output on both dimensions.

**Tables created on startup, not just at build time**
Render's free tier has an ephemeral filesystem. The database is regenerated every time the server starts via `generate_data.py`, and `db.py` runs `init_db()` on import to ensure the `conversations` and `memories` tables always exist.

**Why SQLite**
Zero infrastructure, ships with Python, and the dataset fits in memory. The query interface is identical to Postgres, so swapping the driver is a one-line change.

**Why not stream Claude's response**
The typing indicator covers the latency. Streaming adds complexity for a reply that is 1-2 sentences long.

---

## Voice and tone

The system prompts are the most important part of this project. The rules:

- Lead with what changed, not with context
- Specific numbers always ("287 signups, up 12%" not "signups grew")
- 3-4 sentences for briefs, 1-2 for replies
- End with a question that invites a follow-up
- No bullet points, no headers, no emoji unless the user used one first
- No corporate phrases

This is the same insight behind Linq Blue: a text from a person feels different from a notification from a system, even when the information is identical.

---

## License

MIT
