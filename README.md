# NSE-TRADE (nse-engine)

NSE cash equities on **Angel One SmartAPI** — Book A (MIS intraday) + Book B (CNC swing).
**Paper by default.** Real orders need `MODE=live` **and** `LIVE_ORDERS=true` plus your written yes.

Read `AGENTS.md` and `docs/PLAN.md` first. News/foreign sentiment: `docs/DECISIONS.md` (off until proven).

## Setup

```bash
uv venv --python 3.12 .venv && source .venv/bin/activate
uv pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env   # fill Angel / Telegram locally — never commit
pytest -q && ruff check .
```

## Evening backtest (after you add Angel keys)

```bash
# 1) Read-only key check (no orders)
python -m scripts.login_check

# 2a) Real daily history (preferred for Book B)
python -m scripts.backfill --bhav /path/to/bhavcopy.csv

# 2b) Or synthetic daily until bhav is handy
python -m scripts.seed_demo_daily --years 8

# 3) Run swing research (writes data/reports/ + lab_trials)
python -m scripts.research --strategy S6_swing --symbol SBIN
python -m scripts.research --strategy S6b_keltner --symbol SBIN

# 4) Portal
python -m engine.runner   # http://127.0.0.1:8090/  → PAPER banner
```

Book A (1m) needs Angel candle backfill depth — see plan A2.4 / `scripts/backfill --angel`.

## Shared with crypto (AI + news)

Same Groq / OpenRouter / HF Space keys and optional shared files — see **`docs/SHARED_INFRA.md`**.

```env
# copy from crypto server .env /keys (do not commit)
GROQ_API_KEY=...
OPENROUTER_API_KEY=...
HF_BASE_URL=...
HF_SPACE_API_KEY=...
SHARED_HEADLINES_PATH=/home/ubuntu/shared/headlines.jsonl
SHARED_LLM_BUDGET_PATH=/home/ubuntu/shared/llm_budget.json
NEWS_FILTER_ENABLED=false   # keep false until lab shows lift
```

NSE scrapes India RSS; crypto can append macro headlines to the shared JSONL. Trading DBs stay separate.

## Status

MVP on `feat/mvp-backtest-news`: P0–P4 core + news module + Angel live methods gated off.
See `docs/phase-reports/P0.md` and `docs/phase-reports/P1-P4.md`.
