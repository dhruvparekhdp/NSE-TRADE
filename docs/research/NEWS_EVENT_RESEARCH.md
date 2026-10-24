# V8 — News, events, and rebound research (plan)

**Owner ask (24 Oct 2026):** After V-NEXT, pull **this financial year** market data in detail (Angel + other sources), capture **live microstructure** as fine as the feed allows, **scrape news** that moves names (e.g. security lapses / eMudhra-type headlines), reuse **crypto AI + Hermes-style pipeline** (same API keys per `docs/SHARED_INFRA.md`), run **event studies** (drop → rebound), extend the **watchlist**, and only then **pre-register** tradable rules.

**Not approved for live trading.** Research and paper features only. `news_filter_enabled` stays **false** until lab lift is proven.

---

## 0. Scope and definitions

| Term | Meaning here |
|---|---|
| **Financial year (India)** | FY **2026-27** = **2026-04-01 → 2027-03-31**. “This FY” = from 2026-04-01 through **today** (and rolling forward). |
| **Watchlist** | Nifty 100 (`config/ind_nifty100list.csv`) + `config/watchlist_extra.csv` (owner names, e.g. **EMUDRA** / eMudhra-adjacent tickers — verify NSE symbol). |
| **Event** | Dated headline or exchange filing with `event_type` (see `news/india_rules.py`), symbol link, and severity score. |
| **Hermes (crypto)** | Headline ingest → dedupe (embed) → LLM extract `{symbols, event_type, severity}` → JSONL store. NSE gets a **slim port**, not a copy of crypto DB. |
| **1-second tick** | **Target granularity for research**, not a broker guarantee. Angel SmartAPI **SnapQuote (mode 3)** pushes **quotes when they change**, not a fixed 1 Hz clock. We **bucket** arrivals into **1s OHLCV + spread** bars for FY live capture; plan A7 still avoids storing raw tick firehoses long-term. |

---

## 1. Data plane — FY 2026-27 in detail

### 1.1 Angel One (primary)

| Layer | Source | Storage | Ticket |
|---|---|---|---|
| Daily OHLCV | ONE_DAY candles (`data/angel_daily.py` on `feat/v-fix-2`) | `var/lake` / Parquet daily | Merge F1a into v-next or v8 branch |
| 1-minute history | `data/history.py` 30-day windows, throttled | `bars_1m/SYMBOL/YYYY-MM.parquet` | **V8-D1** backfill all watchlist symbols **2026-04-01 → today** |
| Live stream | `SmartWebSocketV2` SnapQuote | 1m bars (`source=ws`) + optional **1s rollup** | **V8-D2** runner records every session 09:15–15:30 IST |
| Orders / positions | REST (paper only) | SQLite | Already on engine path |

**Acceptance D1:** Report `var/reports/fy_history_depth.md` — per symbol: first/last 1m bar, missing minutes %, API errors.

**Acceptance D2:** After 5 trading days live capture, ≥95% of watchlist symbols have ≥1 tick/minute median during cash session (else document illiquid exclusions).

### 1.2 Other sources (no duplicate secrets)

| Source | Use | Notes |
|---|---|---|
| NSE bhavcopy | Daily backfill 2012+ | Continue resumable download; corp actions file when owner has it |
| NSE / BSE **corporate announcements** | Event timestamps | Scrape or CSV; map ISIN → symbol |
| RSS (existing) | Broad market + stock tags | `news/scrape.py` Moneycontrol / ET |
| **Shared macro lane** | Foreign risk | `SHARED_HEADLINES_PATH` JSONL from crypto |
| Yahoo / Stooq (already in opening study) | Index prior close | Not for order prices |
| India VIX / Nifty index 1m | Regime tags | Join for event-study buckets |

**Out of scope for v1:** Paid Bloomberg/Reuters; full social firehose (X) unless owner adds API budget.

---

## 2. News plane — scrape + AI (Hermes integration)

### 2.1 Ingest (breadth)

**V8-N1** Extend feeds (fixture-tested RSS/HTML parsers):

- NSE “ corporate announcements” and “ security in market” style pages (robots-respecting, slow rate).
- Per-symbol ET / Moneycontrol RSS where stable.
- Append-only JSONL: `data/news/headlines.jsonl` (India) + read `shared/headlines.jsonl`.

Fields: `published_ms`, `source`, `title`, `url`, `raw_snippet`, `symbols[]`, `event_type`, `score`, `confidence`, `embedding_id`.

### 2.2 Hermes-style enrichment (shared keys)

Mirror crypto flow using **existing NSE integrations**:

| Step | Crypto | NSE V8 |
|---|---|---|
| Classify | HF Space `/v1/classify` | `integrations/hf_space.classify` (FinBERT) |
| Embed / dedupe | HF `/v1/embed` + cosine | **V8-N2** `news/dedupe.py` (new; bge-small via same Space) |
| Structured extract | Hermes LLM role | **V8-N3** `news/hermes_extract.py` → `integrations/llm_client.ask_json` role `news_event` |
| Budget | Shared optional | `SHARED_LLM_BUDGET_PATH` |

Prompt output schema (strict JSON):

```json
{
  "symbols": ["EMUDRA"],
  "event_type": "cyber_breach",
  "severity": -0.8,
  "summary": "...",
  "is_company_specific": true
}
```

**Tests:** Fixture headlines (eMudhra-style security lapse, RBI policy, US CPI) — no network.

### 2.3 Link headline → trading day

- Map `published_ms` → **IST session** (plan A9 clock).
- For after-hours news, event day = **next session open** (pre-reg choice; document in `docs/PREREG.md` when strategies exist).

---

## 3. Event study — “drop and rebound” (eMudhra class)

**V8-E1** `lab/event_study.py` (pure functions + tests):

For each `(symbol, event_date, event_type)`:

1. **Abnormal return window:** CAR over **0, +1, +3, +5, +10, +20** sessions vs Nifty 50 beta-adjusted baseline (or market-adjusted for single names).
2. **Intraday path (when 1m exists):** Open gap %, max drawdown day 0, time-under-water, volume spike vs 20d median.
3. **Rebound flags:** Close above event-day open by day **k**; new high within **20d**; % names that fail (stop-out) vs mean-revert.

Cohort filters:

- `event_type in {cyber_breach, fraud, audit_qualification, downgrade, ...}` from `india_rules`.
- Min liquidity: avg daily value ≥ ₹1Cr (setting).
- Exclude confounded days (earnings ±1d unless event is earnings).

**Output:** `var/reports/event_study_fy2627.md` + parquet `data/research/events_fy2627.parquet`.

**Honesty:** Report **survivorship** (today’s Nifty 100), **multiple testing** (count event types tried in `lab/ledger.py`), **partial FY** until history exists.

---

## 4. Strategy hypotheses (pre-register before backtest)

Only after **V8-E1** base rates exist. Draft IDs for owner edit:

| ID | Idea | Entry | Exit | Risk |
|---|---|---|---|---|
| **E1-fade** | Overreaction | Limit buy **−X%** from prior close after `severity ≤ −0.6` company-specific news | Time stop 10d or +Y% | CNC; sector cap; news filter **feature only** until proven |
| **E2-continuation** | Credibility / fraud | Short or skip longs (paper short optional) day 0–1 if gap down & volume spike | Cover 3d or trail | MIS costs — likely paper-only |
| **E3-filter** | Block bad entries | Existing swing rules + `news_score` gate | — | Must beat mirror **with and without** filter in both halves |
| **E4-post-rebound** | Second leg | Donchian / S6 only after day-3 stabilizes (close &gt; event low) | S6 exits | Combined with T1/T6 ledger |

Each trial: `lab/evaluate.py` + mirror + random + cost stress; register in `docs/PREREG.md` **before** run.

---

## 5. Watchlist workflow

1. **`config/watchlist_extra.csv`** — `symbol,reason,added_date` (owner: eMudhra / EMUDRA row).
2. Nightly **V8-W1** job: for each watchlist symbol, pull last 7d headlines, score, append event rows, push Telegram digest (optional).
3. Portal page **Research → Events** (later): table of events + CAR sparklines (read-only).

---

## 6. Phasing and branches

| Phase | Branch | Depends on |
|---|---|---|
| **V8-P0** | `feat/v8-news-p0` | Hermes extract + dedupe + fixtures |
| **V8-P1** | `feat/v8-fy-data` | Angel 1m FY backfill + depth report |
| **V8-P2** | `feat/v8-live-1s` | WS + 1s rollup parquet (RAM cap ≤ plan 600 MB) |
| **V8-P3** | `feat/v8-event-study` | Event catalog + CAR reports |
| **V8-P4** | `feat/v8-strategies` | PREREG E* trials |

**Do not deploy** during market hours. **Do not enable** `live_orders`.

Merge order suggestion: land **F1 paper jobs** (`feat/v-fix-2`) → rebase v8 on top → keep v-next lake work parallel.

---

## 7. Infrastructure (same box as crypto)

Per `docs/SHARED_INFRA.md`:

```bash
# On EC2 (example — keys only in .env)
HF_BASE_URL=...
HF_SPACE_API_KEY=...
GROQ_API_KEY=...
OPENROUTER_API_KEY=...
SHARED_HEADLINES_PATH=/home/ubuntu/shared/headlines.jsonl
SHARED_LLM_BUDGET_PATH=/home/ubuntu/shared/llm_budget.json
```

NSE appends **India equity** headlines to shared file or a sibling `india_headlines.jsonl` that crypto **does not** consume for trading.

Systemd: extend `nse-engine` cron with `job_news` (already stubbed in `engine/runner.py` every 15m 8–16 IST).

---

## 8. Immediate actions (owner / builder)

1. **Let bhav download finish** (now ~826 ok / 2021-04); `build_lake` + full PREREG re-run (V-NEXT closure).
2. **Confirm EMUDRA** NSE symbol and add to `watchlist_extra.csv`.
3. **Point `.env`** at shared HF/Groq paths on server (no keys in git).
4. Open **`feat/v8-news-p0`**: implement `news/hermes_extract.py` + tests + one offline script `scripts/refresh_news_scores.py`.
5. Schedule **FY 1m backfill** overnight (Angel throttle; not in market hours for live WS stress).

---

## 9. Risks

- **Look-ahead:** headline timestamps vs exchange time — test with frozen clocks.
- **Label noise:** LLM mis-tags symbol — require human spot-check sample in phase report.
- **Relevance:** Crypto macro headlines help risk-off; **company-specific** Indian feeds matter more for single-name events.
- **Storage:** 1s × 100 symbols × 6.25h × 250d ≈ tens of GB — keep 1s for **event windows only** (±5d around tagged events) unless owner expands disk.
- **Regulatory:** Scraping terms of use; prefer official NSE announcement APIs/feeds when available.

---

## 10. Success criteria (V8 done)

- FY **2026-04-01 → today**: 1m history depth report green for watchlist.
- ≥ **200** company-specific headlines scored and deduped in JSONL.
- Event study report with **≥30** negative corporate events (pooled or per-type) and rebound statistics **after costs** on simulated E1/E3.
- At least **one** E* trial logged in ledger with honest fail/pass — no strategy enabled without PREREG pass in **both** halves where data exists.

Questions → owner; decisions → `docs/DECISIONS.md`.
