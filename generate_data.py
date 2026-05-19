"""generate_data.py  Produces linqsight.db. Run once. Seed=42 reproducible."""
import sqlite3, random
from datetime import date, timedelta, datetime

random.seed(42)
DB_PATH = "linqsight.db"
TODAY = date(2026, 5, 19)
START = TODAY - timedelta(days=179)

SOURCES       = ["Google Ads", "LinkedIn", "Reddit", "organic", "referral"]
SOURCE_W      = [0.22, 0.30, 0.12, 0.24, 0.12]
DOMAINS       = ["gmail.com","outlook.com","company.io","startup.co","enterprise.com","agency.net","corp.org","tech.ai"]
SIZES         = ["1-10","11-50","51-200","201-1000","1000+"]
SIZE_W        = [0.30, 0.28, 0.22, 0.14, 0.06]
PLANS         = ["starter","growth","pro","enterprise"]
PLAN_MRR      = {"starter":49,"growth":149,"pro":399,"enterprise":999}
PLAN_W        = [0.45, 0.30, 0.18, 0.07]
VIRAL_DAY     = TODAY - timedelta(days=random.randint(8, 25))


def base_signups(d: date) -> float:
    days_in = (d - START).days
    base = 55 * (1 + 0.015 / 7 * days_in)
    if d.weekday() >= 5:
        base *= 0.70
    return base


def build_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # ── schema ────────────────────────────────────────────────────────────────
    c.executescript("""
    DROP TABLE IF EXISTS signups;
    DROP TABLE IF EXISTS activations;
    DROP TABLE IF EXISTS conversions;
    DROP TABLE IF EXISTS ad_spend;
    DROP TABLE IF EXISTS experiments;
    DROP TABLE IF EXISTS conversations;
    DROP TABLE IF EXISTS memories;

    CREATE TABLE signups (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        date          TEXT NOT NULL,
        source        TEXT NOT NULL,
        email_domain  TEXT NOT NULL,
        company_size  TEXT NOT NULL
    );

    CREATE TABLE activations (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        signup_id       INTEGER NOT NULL,
        activated_at    TEXT NOT NULL,
        activation_event TEXT NOT NULL
    );

    CREATE TABLE conversions (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        signup_id    INTEGER NOT NULL,
        converted_at TEXT NOT NULL,
        plan         TEXT NOT NULL,
        mrr          REAL NOT NULL
    );

    CREATE TABLE ad_spend (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        date        TEXT NOT NULL,
        channel     TEXT NOT NULL,
        spend       REAL NOT NULL,
        impressions INTEGER NOT NULL,
        clicks      INTEGER NOT NULL
    );

    CREATE TABLE experiments (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        start_date TEXT NOT NULL,
        end_date   TEXT NOT NULL,
        name       TEXT NOT NULL,
        variant_a  TEXT NOT NULL,
        variant_b  TEXT NOT NULL,
        winner     TEXT
    );

    CREATE TABLE conversations (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        sender     TEXT NOT NULL,
        role       TEXT NOT NULL,   -- 'user' or 'assistant'
        content    TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    );

    CREATE TABLE memories (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        key        TEXT NOT NULL,
        value      TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    );
    """)

    # ── signups ───────────────────────────────────────────────────────────────
    signup_id = 0
    signup_rows = []
    activation_rows = []
    conversion_rows = []

    for i in range(180):
        d = START + timedelta(days=i)
        mu = base_signups(d)

        # Reddit viral spike
        if d == VIRAL_DAY:
            mu *= random.uniform(3.2, 4.5)

        count = max(1, int(random.gauss(mu, mu * 0.12)))

        for _ in range(count):
            signup_id += 1
            source = random.choices(SOURCES, SOURCE_W)[0]
            domain = random.choice(DOMAINS)
            size = random.choices(SIZES, SIZE_W)[0]
            signup_rows.append((d.isoformat(), source, domain, size))

            # activation rates by source
            act_rates = {
                "Google Ads": 0.52,
                "LinkedIn": 0.31,   # lowest
                "Reddit": 0.44,
                "organic": 0.61,
                "referral": 0.68,
            }
            if random.random() < act_rates[source]:
                delay_h = random.randint(1, 72)
                act_ts = datetime.combine(d, datetime.min.time()) + timedelta(hours=delay_h)
                event = random.choice(["connected_integration", "sent_first_message",
                                       "invited_teammate", "completed_onboarding"])
                activation_rows.append((signup_id, act_ts.isoformat(), event))

                # conversion (subset of activated)
                conv_rate = 0.22
                if random.random() < conv_rate:
                    conv_delay = random.randint(1, 14)
                    conv_ts = act_ts + timedelta(days=conv_delay)
                    plan = random.choices(PLANS, PLAN_W)[0]
                    mrr = PLAN_MRR[plan] * random.uniform(0.95, 1.05)
                    conversion_rows.append((signup_id, conv_ts.isoformat(), plan, round(mrr, 2)))

    c.executemany(
        "INSERT INTO signups (date, source, email_domain, company_size) VALUES (?,?,?,?)",
        signup_rows,
    )
    c.executemany(
        "INSERT INTO activations (signup_id, activated_at, activation_event) VALUES (?,?,?)",
        activation_rows,
    )
    c.executemany(
        "INSERT INTO conversions (signup_id, converted_at, plan, mrr) VALUES (?,?,?,?)",
        conversion_rows,
    )

    # ── ad_spend ──────────────────────────────────────────────────────────────
    ad_rows = []
    for i in range(180):
        d = START + timedelta(days=i)
        # Google Ads: CAC spikes ~22% in last 7 days (new creative underperforms)
        google_base = random.gauss(420, 30)
        if (TODAY - d).days <= 7:
            google_base *= 1.22
        g_clicks = max(10, int(random.gauss(180, 20)))
        g_impr = g_clicks * random.randint(18, 28)
        ad_rows.append((d.isoformat(), "Google Ads", round(google_base, 2), g_impr, g_clicks))

        li_base = random.gauss(310, 25)
        li_clicks = max(5, int(random.gauss(90, 12)))
        li_impr = li_clicks * random.randint(22, 35)
        ad_rows.append((d.isoformat(), "LinkedIn", round(li_base, 2), li_impr, li_clicks))

    c.executemany(
        "INSERT INTO ad_spend (date, channel, spend, impressions, clicks) VALUES (?,?,?,?,?)",
        ad_rows,
    )

    # ── experiments ───────────────────────────────────────────────────────────
    # Month 3 experiment that clearly won
    exp_start = START + timedelta(days=60)
    exp_end = exp_start + timedelta(days=21)
    c.execute(
        "INSERT INTO experiments (start_date, end_date, name, variant_a, variant_b, winner) "
        "VALUES (?,?,?,?,?,?)",
        (
            exp_start.isoformat(), exp_end.isoformat(),
            "Onboarding v2",
            "Original 5-step onboarding",
            "Streamlined 3-step onboarding with video",
            "variant_b",
        ),
    )
    # A more recent inconclusive experiment
    exp2_start = TODAY - timedelta(days=18)
    exp2_end = TODAY - timedelta(days=4)
    c.execute(
        "INSERT INTO experiments (start_date, end_date, name, variant_a, variant_b, winner) "
        "VALUES (?,?,?,?,?,?)",
        (
            exp2_start.isoformat(), exp2_end.isoformat(),
            "Pricing Page CTA",
            "Start free trial",
            "See it in action",
            None,
        ),
    )

    conn.commit()
    conn.close()

    total_signups = len(signup_rows)
    total_activations = len(activation_rows)
    total_conversions = len(conversion_rows)
    print(f"✓ linqsight.db created")
    print(f"  {total_signups:,} signups | {total_activations:,} activations | {total_conversions:,} conversions")
    print(f"  Viral day: {VIRAL_DAY.isoformat()}")
    print(f"  CAC spike window: last 7 days before {TODAY.isoformat()}")


if __name__ == "__main__":
    build_db()
