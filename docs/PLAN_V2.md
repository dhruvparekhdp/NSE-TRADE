# PLAN V2: make the NSE engine the crypto engine's twin

Written 23 Oct 2026 by Claude (planner) for Cursor (builder). The owner's brief: "make it similar in UI, paper
trading and basic concept; only market-related things change", and "Claude plans everything in detail, Cursor
does the hard work".

**How to use this file (Cursor):** read `AGENTS.md`, then this file, then `docs/MARKET_INDIA.md` (the market facts
this plan relies on). `docs/PLAN.md` still holds, except where this file says otherwise. Where they disagree,
this file wins (owner decision, logged in `docs/DECISIONS.md` on 23 Oct 2026). Work one phase per branch, one PR
per phase. Every ticket has a test that fails before and passes after. Ask the owner, don't guess, when
§11 lists the question as open. Use the default written there until answered.

The reference implementation is the owner's crypto engine on this Mac:
`/Users/dhruv/personal/Tennis-bet/crypto-signal-engine` (public repo). Copy its front-end and ideas freely into this
private repo. Never copy anything from this repo into that one.

---

## 1. What "similar to crypto" means

The crypto engine reached its current shape through a lot of evidence: one swing book that is allowed to paper
trade, intraday quarantined to shadow, every signal logged with mirror and random baselines, every signal
replayed to an outcome (traded or not), filters audited as "taken vs skipped", a wallet-based paper cycle, a
go-live checklist, and a four-hub "Brutal Command" portal. The NSE engine copies all of that. Only the market
layer is different.

| Concept | Crypto engine (reference) | NSE engine (target) |
|---|---|---|
| The book that paper trades | Swing book: 4h/8h breakouts, stop 3×ATR, target 3R, 7-day limit (`analysis/swing_book.py`) | **Book B**: daily breakouts S6/S6b (PLAN A10), CNC, long only, stop 2.5×ATR14 trailed, 20-session limit |
| Quarantined family | 15m detectors run shadow only | **Book A** (S1–S5 intraday MIS) runs **shadow only**: signals and virtual outcomes, no paper trades, until it passes the gate (§2 D2) |
| Market filter | Skip swing signals when BTC 30-day vol is in the top third of its past year (`analysis/regime_gate.py`) | Same idea on **Nifty 50** 30-day realised vol, as a pre-registered **trial** first (V3), not switched on by assumption |
| Paper wallet | Paper cycle: starting wallet, target wallet, peak, equity, unrealised, hit rate, net P&L, costs (`analysis/paper_cycle.py`, Book › Paper cycle) | Same cycle object in ₹. Costs split into brokerage, STT, exchange, SEBI, stamp, GST, DP, slippage |
| Fill rule shared by backtest and paper | `resolve_candle` / `virtual_outcome` | New `core/exits.py`, used by the backtest, the paper engine and the outcome replay (V2-7) |
| Every signal resolved | `_swing_outcomes_job` replays traded and skipped signals | `job_outcomes` replays every pick, mirror, random and skipped signal on daily bars |
| Costs | Fees + 18% GST + slippage + funding | STT, stamp, exchange, SEBI, GST, DP, brokerage with min ₹5, slippage (`MARKET_INDIA.md` §5) |
| Sessions | 24/7 | Pre-open, continuous, closing auction, holidays, Muhurat. Times are dated and per stock class (`MARKET_INDIA.md` §2) |
| Leverage | Up to 10x | None for CNC. MIS ≤5x (shadow only for now) |
| Shorting | Either side | CNC long only. MIS either side |
| Settlement | Instant | T+1. Book B holds at least one night |
| Data | Binance klines + WS | NSE bhavcopy (UDiFF) + Angel SmartAPI candles, quotes and WS. Yahoo only for the ticker tape |
| Portal | 4 hubs: Command / Book / Evidence / System; micro-UI `core.js`; 4 palettes | Same hubs, pages, components and palettes; NSE data |
| Go-live | System › Go-live gates page | Same page, with NSE gates (§8) |
| Alerts | Telegram | Telegram, separate bot (unchanged) |

## 2. Decisions this plan proposes (owner confirms in §11)

- **D1. Book B paper trades first, on end-of-day data.** Signals are computed on the daily close and filled the
  next day by exactly the backtest's daily fill rule. Paper doesn't depend on a live tick feed, and paper equals
  backtest by construction (crypto lesson 4).
- **D2. Book A runs shadow only** (like crypto's 15m detectors). PLAN A2's own numbers mean Book A can't size a
  trade at ₹50k: the ₹1L minimum with 1% risk needs a stop of 0.5% or less, which costs 0.29R. It runs on the
  live Angel feed in V6, logs signals and virtual outcomes, and is promoted only through the gate.
- **D3. Paper capital ₹1,00,000** with 1% risk. That gives ₹20k-plus CNC positions at about a 5% stop. At ₹50k
  and 5 slots each position is ₹10k, and costs reach 0.79% a round trip (`MARKET_INDIA.md` §5). New setting
  `min_position_cnc_inr = 20000`.
- **D4. Square off ≥15 minutes before the broker's cut-off,** derived from one setting, not hard-coded. CAS moved
  brokers' cut-offs to about 15:00–15:10 for F&O stocks until 6 Dec 2026.
- **D5. Lab first, then filters.** The Nifty vol filter, a trend filter and one momentum strategy are added as
  pre-registered trials (V3). Nothing is switched on without passing the gate.
- **D6. One fill/exit engine** (`core/exits.py`) for backtest, paper and outcome replay.
- **D7. The portal is a port of crypto's micro-UI** (Store, widgets, views, components, palettes), with NSE data
  behind the same kind of JSON endpoints.
- **D8. Track the whole opening and the market's mood every day, from as early as possible** (owner, 23 Oct
  2026: "market opening is a very big thing, so track entire sentiment with GIFT Nifty, US and Europe market,
  war news, every major thing"). Record global cues, GIFT Nifty, FII/DII, India VIX, tagged major-event
  headlines, the 09:00–09:15 pre-open auction and the first 30 minutes. Pre-open and live breadth can't be
  downloaded later, so this is phase **V1b**, right after V1. It is **information and research data**: it never
  blocks or sizes a trade until a pre-registered lab trial shows lift (crypto: news echoed price 48/48).

## 3. Review: where the app is today

### 3.1 What works

- Settings, the dual live flags and the pytest guard. Live order methods are hard-gated (`broker/angel.py:107-110`).
- Cost model formulas (`core/costs.py`) match Angel's structure. Only the rates need refreshing (V1-4).
- Indicators (SMA, EMA, Wilder ATR and RSI, VWAP, Donchian, Keltner), SQLite migrations, ledger, keys page with an
  encrypted store, Telegram client, market-hours deploy guard.
- Tests: 54 pass. Ruff has 2 errors (unused imports in `scripts/_remote_check_keys_quotes.py:6` and
  `scripts/login_check.py:19`), so CI is red.

### 3.2 What isn't there yet

- **No paper trading runs.** Every trading job in `engine/runner.py:34-59` only logs. `/api/today` returns zeros
  (`web/portal_api.py:29-33`). `/api/health` hard-codes `login_ok: false` (`web/app.py:38`).
- **All research data is synthetic.** Every file in `data/lake/bars_1d/` has `source == "synth"`. The S6 report
  (45 trades, −0.26R) is a smoke test, not evidence.
- **The portal is a skin with placeholders.** It has the crypto look and four hubs, but none of crypto's pages
  (swing positions in R, paper cycle tiles, signals with "why refused", taken vs skipped, go-live gates, session
  guard, accuracy, history), one palette instead of four, and no component kit.
- **Nothing is committed.** The whole tree is untracked on `feat/mvp-backtest-news` (only "Initial commit" exists).

### 3.3 Bugs (confirmed by running probes on 23 Oct 2026 unless marked "by reading")

| # | Severity | Where | What is wrong | Fixed in |
|---|---|---|---|---|
| B1 | critical | `lab/backtest.py:189-197` | Intraday backtest checks the stop **only for longs**. A gap-fade short with its stop at 103.2 ran to 120.6: **−30R** recorded as one "square_off" trade | V2-2 |
| B2 | high | `lab/backtest.py:157-230` | Intraday targets and `time_exit_ms` are ignored. Square-off happens at the last bar (15:29 in the probe), not 15:05. An ORB trade that reached 2R was held to the close | V2-2 |
| B3 | critical | `lab/backtest.py:78-83` | Daily stops always fill **at the stop price, even when the day opens far below it**. Probe: a −20% gap recorded −1.46R where the real fill (at the open) is about −10.6R. Backtests look far safer than reality | V2-1 |
| B4 | high | `lab/backtest.py:114-124` | Daily entry assumes the next-day LIMIT (close +0.5%) always fills at that price. No check that the next day traded down to it, no better fill when it opens below, `entry_ms` set on the signal day. The trailing stop (PLAN A10) is missing | V2-1 |
| B5 | critical | `scripts/research.py:38-73` | **Mirror and random baselines are made up**: mirror R = −pick R, random R = 0. The gate's "beats mirror / beats random" checks reduce to "average R > 0". This breaks crypto lesson 2 | V2-4 |
| B6 | high | `scripts/research.py`, `lab/backtest.py:49` | Research runs one symbol at a time with its own capital. The n ≥ 100 per half gate can never be met, and there's no portfolio (shared cash, max open, priority) | V2-5 |
| B7 | critical | `broker/paper.py:154-161` | Paper MIS close returns only the margin. **Profit and loss never reach cash** (probe: +₹10,000 trade, cash unchanged at ₹1,00,000). Costs are never deducted. Partial reduces don't touch cash. Delivery buys can push cash negative | V4-3 |
| B8 | high | `core/orders.py:239` | The stop watchdog measures the stop order's age, not how long price has been through the trigger. It forces an exit on the **first** crossing tick if the stop is more than 10 s old (probe confirmed). PLAN A9.4 says "crossed for longer than `stop_watchdog_s`" | V4-5 |
| B9 | high | `core/orders.py:92,95,140,142,255` | Prices are rounded to 2 decimals, not the tick (probe: 1235.18 and 1216.11, invalid on a ₹0.10 tick). Breaks AGENTS rule 8. The exchange rejects such orders | V0-4 |
| B10 | medium | `core/orders.py:96-100` | "Idempotent by tag" can't work: a new tag is generated, then looked up | V4-5 |
| B11 | high | `core/orders.py:114` vs `broker/angel.py:112,128` | Order manager calls `place_order(**kwargs)` / `cancel_order(client_tag)`. Angel takes `place_order(params: dict)` / `cancel_order(order_id, variety)`. `broker/base.py` is an empty async stub while both brokers are sync. "Paper uses exactly the live code path" isn't true yet | V4-5 |
| B12 | medium | `core/orders.py:268-276` | `square_off` cancels the stop and target but sends no exit | V4-5 |
| B13 | high (by reading) | `strategies/base.py:23-24` | `BarView.closed()` treats every bar as closed 60 s after its open. A daily bar stamped 09:15 counts as closed at 09:16, so a daily strategy run live would see the day's high, low and close hours early | V2-3 |
| B14 | high (by reading) | `strategies/orb.py:43-50`, `vwap_revert.py`, `intraday_momentum.py` | Strategies are fed 1m bars, but the rules are 5m/15m. ORB uses a 1m close and 1m volume against a 5m slot average. ATR is on 1m bars where PLAN says 5m | V2-2 |
| B15 | critical (by reading) | `strategies/gap.py`, `pdh_rs.py`, `intraday_momentum.py`, `orb.py` | **Nothing ever supplies `prev_close`, `pdh`, `rs_rank`, `ret_decile`, `slot_vol_avg` or `gap_pct`** (no caller in `lab/`, `engine/`, `scripts/` or `tests/`). S3, S3b, S4 and S5 can never fire. S1's volume filter is silently skipped, so it isn't the pre-registered rule | V2-2 |
| B16 | high | `core/clock.py:55-102` | One fixed 15:30 close for every stock. Since 3 Aug 2026, F&O stocks stop continuous trading at 15:15 (CAS), and from 7 Dec 2026 at 15:30 with CAS to 15:40. No pre-open phases | V1-1 |
| B17 | high | `config/holidays_2026.json:23-32` | Muhurat placeholder 18:15–19:15. The real 2026 session is in the **afternoon** (14:20 start) | V1-2 |
| B18 | high | `data/calendar.py:77-80` | Only the 2026 file loads. From 1 Jan 2027 every weekday counts as a trading day. The runner's cron (`engine/runner.py:93-105`) runs Mon–Fri jobs on holidays too | V1-2 |
| B19 | high | `settings.py:61-62`, PLAN A3 | Square-off 15:05 can be later than Angel's post-CAS cut-off (reported 15:10 or earlier for F&O stocks) | V1-3 |
| B20 | medium | `config/costs_angel.json:10` | NSE transaction charge 0.00297%. Current tables show 0.00307%. Brokerage minimum ₹5 not modelled. `verified_against_calculator: false` | V1-4 |
| B21 | high | `data/history.py:23-50` | Bhavcopy parser reads only the legacy columns. NSE's file has been UDiFF since July 2024. No split/bonus/dividend adjustment anywhere, so a 1:1 bonus looks like a −50% gap | V1-7 |
| B22 | medium | `data/free_quotes.py:22` | "Live" quotes are Yahoo daily candles (`interval=1d&range=5d`), delayed and unofficial, for 20 symbols. Fine for the tape, unusable for fills | V4-2 |
| B23 | medium | `scripts/research.py:25`, `engine/runner.py:26` | Research writes to `./data/engine.db`. The portal reads `./var/engine.db` (`settings.data_dir`), so research trials never show on the Lab page | V0-5 |
| B24 | high | `config/settings.py:76`, DECISIONS 23 Oct | Portal binds `0.0.0.0` and is served publicly over **plain HTTP** (`http://52.62.37.4/nse/`). The admin password and Angel keys typed on `/keys` cross the internet unencrypted. Cookie has no `Secure` flag. PLAN A13 said Tailscale only | V0-2 |
| B25 | low | `core/orders.py:87,148` and similar | `now_ms or time.time()` treats 0 as missing (a test at ms=0 silently uses wall time) | V0-3 |
| B26 | low | `core/risk.py:104-107` | MIS exposure check ignores the new position's own value | V1-5 |
| B27 | low | `engine/runner.py:61-78` | News job ingests an empty list (never fetches). Fine while news is off. Leave it off | — |

## 4. Target architecture (what changes, file by file)

```
config/
  sessions.json            NEW  dated session regimes per stock class (V1-1)
  holidays_2026.json       FIX  Muhurat afternoon; schema adds "verified_by_owner" date (V1-2)
  holidays_2027.json       NEW  when NSE publishes (owner), loader requires it from 1 Jan 2027
  costs_angel.json         FIX  rates, min brokerage, source + date, verified_against_contract_note (V1-4)
  tick_bands.json          NEW  fallback tick table (MARKET_INDIA §4) (V0-4)
  universe_history.csv     NEW  Nifty 100 adds/removes with dates (V1-6)
  surveillance.json        NEW  ASM/GSM exclusions, refreshed daily (V1-5)
core/
  ticks.py                 NEW  round_to_tick(price, tick, direction) (V0-4)
  clock.py                 FIX  session_state(ms, *, stock_class) reads sessions.json (V1-1)
  exits.py                 NEW  the one fill/exit engine (V2-7)
  costs.py                 FIX  min brokerage; breakdown incl. slippage (V1-4)
  risk.py                  FIX  min_position_cnc_inr, exposure incl. new position, surveillance (V1-5)
  orders.py                FIX  tick rounding, real idempotency, watchdog timing, square-off exit (V4-5)
broker/
  base.py                  FIX  real sync Broker protocol + dataclasses (Order, Fill, Position, Funds, Quote) (V4-5)
  paper.py                 FIX  cash/P&L/costs accounting; CNC long-only; T+1 holding rule (V4-3)
  angel.py                 FIX  adapter to the Broker protocol (tag → order id map) (V4-5)
data/
  history.py               FIX  UDiFF + legacy bhavcopy, delivery file, corporate actions (V1-7)
  corporate_actions.py     NEW  adjustment factors (V1-7)
  events.py                NEW  results dates, expiry Tuesdays, RBI MPC, Budget (V1-8)
  quotes.py                NEW  Angel LTP poller for marking; Yahoo fallback for the tape (V4-2)
  global_cues.py           NEW  US / Europe / Asia indices + futures, USD/INR, DXY, Brent, gold, US 10y, GIFT Nifty (V1b-1)
  preopen.py               NEW  NSE pre-open snapshots (IEP, buy/sell qty) every 30 s, 09:00–09:15 (V1b-2)
  flows.py                 NEW  FII/DII provisional cash flows each evening (V1b-1)
news/
  india_rules.py           FIX  new event tags: geopolitics_india, middle_east, russia_ukraine, tariffs_trade, us_data,
                                china, opec, monsoon, gst_council, india_macro, block_deal, promoter_pledge (V1b-3)
  scrape.py                FIX  real fetch on a schedule, more feeds, published time from the feed (V1b-3)
engine/
  opening.py               NEW  morning brief, opening scorecard, opening type label, risk-off alarm (V1b-4)
lab/
  backtest.py              REWRITE on core/exits.py; portfolio mode across the universe (V2)
  baselines.py             NEW  real mirror + random trades (V2-4)
  evaluate.py              FIX  halves, by year, VIX tercile, results season, cost stress (V2-6)
  prereg.py + docs/PREREG.md NEW  trial definitions written before runs (V3-2)
engine/
  paper_engine.py          NEW  Book B EOD cycle: scan → prepare → fill → exits → mark (V4)
  outcomes.py              NEW  resolve every signal (taken/skipped/mirror/random) (V4-4)
  runner.py                FIX  real jobs, calendar-aware (V4-6)
  migrations/002_paper.sql NEW  §5
web/
  portal/ (core.js, portal.css, portal.html, nav.js, hubs/*.js)   PORT from crypto (V5)
  portal_api.py            FIX  the endpoints in §7
```

## 5. Data model changes (`engine/migrations/002_paper.sql`)

```sql
CREATE TABLE paper_cycles (
  id INTEGER PRIMARY KEY, started_ms INTEGER NOT NULL, ended_ms INTEGER,
  starting_wallet REAL NOT NULL, target_wallet REAL, wallet REAL NOT NULL, peak_wallet REAL NOT NULL,
  status TEXT NOT NULL DEFAULT 'running',          -- running | target_hit | floor_hit | stopped
  outcome TEXT, config_json TEXT NOT NULL           -- the exact rules in force when the cycle started
);
ALTER TABLE trades ADD COLUMN cycle_id INTEGER;
ALTER TABLE trades ADD COLUMN costs_json TEXT;      -- {brokerage, stt, exchange, sebi, stamp, gst, dp, slippage}
ALTER TABLE trades ADD COLUMN mfe_r REAL;           -- best R reached
ALTER TABLE trades ADD COLUMN mae_r REAL;           -- worst R reached
ALTER TABLE trades ADD COLUMN sessions_held INTEGER;
ALTER TABLE trades ADD COLUMN note TEXT;
ALTER TABLE signals ADD COLUMN virtual_status TEXT; -- running | resolved | no_fill
ALTER TABLE signals ADD COLUMN virtual_exit_reason TEXT;
ALTER TABLE signals ADD COLUMN virtual_r REAL;      -- after costs, same exit engine as real trades
ALTER TABLE signals ADD COLUMN resolved_ms INTEGER;
ALTER TABLE signals ADD COLUMN filter_tag TEXT;     -- e.g. "nifty_vol_rank=0.81" (crypto regime tag)
CREATE TABLE pending_orders (                       -- Book B entries prepared in the evening for tomorrow
  id INTEGER PRIMARY KEY, signal_id INTEGER NOT NULL, trade_date TEXT NOT NULL, symbol TEXT NOT NULL,
  side INTEGER NOT NULL, qty INTEGER NOT NULL, limit_price REAL NOT NULL, stop REAL NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending', created_ms INTEGER NOT NULL
);
```

`lab_trials` also gets `prereg_id TEXT`, `data_hash TEXT` and `post_hoc INTEGER DEFAULT 0` (today `post_hoc` is
hidden inside `params_json`, `lab/ledger.py:33-35`).

Opening and sentiment tables (`engine/migrations/003_opening.sql`, phase V1b):

```sql
CREATE TABLE global_cues (            -- one row per instrument per snapshot
  ts_ms INTEGER NOT NULL, key TEXT NOT NULL,          -- "SPX", "NDX", "ES", "DAX", "FTSE", "N225", "USDINR", "BRENT", "GIFTNIFTY" ...
  last REAL, chg_pct REAL, ref_close REAL, source TEXT NOT NULL, stale INTEGER DEFAULT 0,
  PRIMARY KEY (ts_ms, key)
);
CREATE TABLE flows (trade_date TEXT PRIMARY KEY, fii_net_cr REAL, dii_net_cr REAL, source TEXT, final INTEGER DEFAULT 0);
CREATE TABLE headlines (
  id INTEGER PRIMARY KEY, ts_ms INTEGER NOT NULL, published_ms INTEGER, source TEXT, title TEXT NOT NULL, link TEXT,
  event_type TEXT, symbol TEXT, score REAL, confidence REAL, market TEXT, external_id TEXT UNIQUE
);
CREATE TABLE preopen_snapshots (
  trade_date TEXT NOT NULL, ts_ms INTEGER NOT NULL, symbol TEXT NOT NULL,   -- "NIFTY" for the index
  iep REAL, prev_close REAL, chg_pct REAL, buy_qty INTEGER, sell_qty INTEGER, final INTEGER DEFAULT 0, source TEXT,
  PRIMARY KEY (trade_date, ts_ms, symbol)
);
CREATE TABLE opening_summary (
  trade_date TEXT NOT NULL, symbol TEXT NOT NULL, open REAL, prev_close REAL, gap_pct REAL,
  imbalance REAL,                                      -- (buy_qty - sell_qty) / (buy_qty + sell_qty) at the final pre-open
  or15_high REAL, or15_low REAL, or30_high REAL, or30_low REAL, first5_vol_x REAL,
  gap_filled_ms INTEGER, close REAL, open_to_close_pct REAL, open_type TEXT,
  PRIMARY KEY (trade_date, symbol)
);
CREATE TABLE morning_brief (trade_date TEXT PRIMARY KEY, built_ms INTEGER, json TEXT NOT NULL);  -- frozen at 08:45
CREATE TABLE sentiment_daily (
  trade_date TEXT PRIMARY KEY, composite REAL, parts_json TEXT NOT NULL,   -- each component, its weight, its value
  breadth_adv INTEGER, breadth_dec INTEGER, risk_off_alarm INTEGER DEFAULT 0
);
```

## 6. New and changed settings (`config/settings.py`; never touch `mode` / `live_orders` defaults)

| Name | Default | Why |
|---|---|---|
| `capital_inr` | 100000 | D3 (paper capital; live reads funds from Angel) |
| `min_position_cnc_inr` | 20000 | Book B cost floor (MARKET_INDIA §5) |
| `book_a_mode` | "shadow" | D2. Values: off / shadow / paper |
| `broker_squareoff_at` | "15:10" | D4. Owner confirms Angel's cut-off (Q1) |
| `squareoff_lead_min` | 15 | engine square-off = broker − lead |
| `no_entry_lead_min` | 20 | no new entries = engine square-off − lead |
| `paper_target_wallet` | 0 (none) | crypto-style cycle target, optional |
| `market_filter` | "off" | "off" / "nifty_vol" / "nifty_trend". On only after the V3 gate |
| `market_filter_vol_rank_max` | 0.667 | crypto's "top third" rule |
| `web_host` | "127.0.0.1" | B24 |
| `cookie_secure` | true | B24 (false only for local http dev) |
| `opening_tracker_enabled` | true | D8. Recording only, never a trade filter |
| `preopen_snapshot_s` | 30 | pre-open poll interval |
| `cues_poll_s` | 300 | global cues every 5 min, 06:00–23:30 IST |
| `risk_off_brent_pct` / `risk_off_vix_pct` / `risk_off_window_min` | 3.0 / 10.0 / 120 | risk-off alarm rule (MARKET_INDIA §8b) |
| `gift_nifty_source` | "none" | "none" / "url" / "paid". Until set, US futures + Asia are the overnight proxy (Q11) |

`square_off_at` and `no_entry_after` become derived values, shown on the portal. Tests assert the engine
square-off is always at least `squareoff_lead_min` before `broker_squareoff_at`.

## 7. API contract for the portal (JSON shapes the front end codes against)

The front end is built against these shapes. V5 can start with fixtures in `tests/fixtures/portal/*.json` before
the engine fills them. All times are UTC epoch ms; the browser shows IST.

```
GET /api/portal/meta     {mode, live_orders, kill_switch, book_a_mode, market_filter,
                          session: {state, stock_class, label, next_change_ms, next_label},
                          calendar_ok, calendar_year_loaded, costs_verified, capital_inr,
                          squareoff_at, no_entry_after, broker_squareoff_at, version}
GET /api/quotes          {ts_ms, source, quotes: [{symbol, ltp, prev_close, chg_pct, volume}]}   (tape)
GET /api/market          {nifty: {ltp, chg_pct}, india_vix, nifty_vol_rank, nifty_above_200dma,
                          fii_net_cr, dii_net_cr, gift_nifty_chg_pct|null, next_events: [{kind, date, label}]}
GET /api/swing           {rules: {timeframe, stop, trail, time_limit_sessions, risk_pct, min_position_inr,
                                  max_open, market_filter, excluded},
                          open: [{trade_id, symbol, strategy, qty, entry, stop_init, stop_now, mark,
                                  r_now, unrealised_inr, sessions_held, sessions_left, entry_ms}],
                          closed: {n, win_rate, avg_r, total_r, last: [{symbol, strategy, r, net_inr,
                                   costs_inr, exit_reason, entry_ms, exit_ms}]},
                          takeskip: {take: {n, running, avg_r}, skip: {n, running, avg_r}}}
GET /api/paper           {enabled, running,
                          cycle: {id, started_ms, starting_wallet, target_wallet, wallet, peak_wallet},
                          equity, unrealised, positions: [...same as swing.open + book],
                          summary: {trades, win_rate_pct, net_pnl, expectancy_per_trade,
                                    costs: {brokerage, stt, exchange, sebi, stamp, gst, dp, slippage}},
                          history: [{...closed trade, book}]}
GET /api/portal/signals?days=14&book=&strategy=&role=&decision=
                         {rows: [{id, ts_ms, symbol, book, strategy, role, side, price, stop, target,
                                  decision, skip_reason, reason_text, virtual_status, virtual_r}],
                          refused: [{reason, reason_text, n}]}
GET /api/lab             {trials_total, strategies: [{id, book, last_report: {gate fields...}, trials,
                          passed, prereg_id}]}
GET /api/golive          {verdict, gates: [{id, label, ok, detail}]}
GET /api/guard           {session, feed: {last_tick_age_s, stale}, reconcile_faults: [...],
                          daily_loss_pct, floor_ok, kill_switch, flags: [{id, on, text}]}
GET /api/data-health     {lake: {symbols, first_date, last_date, missing_days: [...]},
                          bhav: {last_date, format}, corp_actions_applied, minutes_today: {...}}
GET /api/opening         {trade_date, phase: "overnight"|"preopen"|"opening"|"day"|"closed",
                          brief: {gift_nifty: {chg_pct, ts_ms}|null, us: [...], europe: [...], asia: [...],
                                  fx_commod: [...], fii_net_cr, dii_net_cr, india_vix, top_headlines: [...],
                                  results_today: [...], events_today: [...], composite, built_ms},
                          preopen: {nifty: {iep, chg_pct, imbalance}, snapshots_n, last_ms,
                                    movers: [{symbol, iep, chg_pct, imbalance}]},
                          scorecard: {nifty_gap_pct, gap_filled_ms|null, or15: [lo, hi], breadth: {adv, dec},
                                      first5_vol_x, open_type|null},
                          history: [{trade_date, nifty_gap_pct, imbalance, open_type, open_to_close_pct}]}
GET /api/sentiment       {composite, label, parts: [{key, label, value, weight, contribution, ts_ms, stale}],
                          markets: [{key, label, region, last, chg_pct, ts_ms, stale}],
                          risk_off_alarm: {on, since_ms, reasons: [...]},
                          timeline: [{ts_ms, nifty_chg_pct, composite}]}
GET /api/headlines?hours=24&tag=&symbol=
                         {rows: [{ts_ms, source, title, link, event_type, symbol, score, nifty_move_next_60m|null}],
                          tags: [{event_type, n}]}
GET  /api/keys           (admin) {rows: [{key, label, kind, is_set, where, masked, length, fingerprint, saved_ms,
                          history: [{masked, fingerprint, saved_ms, saved_by}]}], secure_channel: bool}
POST /api/keys/compare   (admin, secure channel) {key, value} -> {match: bool, first_diff_at: int|null}
POST /api/keys/reveal    (admin + password, secure channel) {key, password} -> {value}   no-store, audited, 5 per 10 min
GET /api/events?limit=   audit events
GET /api/tables          (admin) newest rows per table, like crypto's System › Data
```

`reason_text` maps every machine reason to plain English in one dict (`web/reasons.py`). For example,
`below_min_position` → "position under ₹20,000: costs would eat too much", `near_circuit` → "too close to
today's price band", `results_day` → "results due within 3 days", `market_filter` → "Nifty volatility in the
top third of the past year".

## 8. Portal: pages and widgets (port of crypto `scheduler/portal/`)

Keep hash routing (`#/book/paper`) because the portal is served under `/nse/`. Everything else follows
`crypto/docs/PORTAL_REVAMP.md`: the Store (poll only while a widget uses a key, pause in hidden tabs), widgets,
views, the component kit `UI.C`, the four palettes (Sage & Lilac default, Champagne & Teal, Ice & Peach,
Classic lime) with header swatches and `localStorage`, motion only as decoration, `prefers-reduced-motion`, and
**nothing simulated on the real portal**.

**Seven pages, not twenty-one** (owner, 23 Oct 2026: "cut them short to only required, or club them"). The four
crypto hubs stay, so the portal looks and navigates like crypto. Each hub holds only the pages that earn their
place. Anything that was only another view of the same data is now a section or filter on one page.

| Hub | Page (route) | What it clubs | Sections, top to bottom |
|---|---|---|---|
| 01 Command | **Today** (`#/command`) | Overview + Session guard + Live ₹ status | session hero (state, countdown to next change, square-off and no-entry times, kill switch); pipeline (data → strategies → risk → paper book → opening recorder); wallet mini-tiles (equity, today's P&L, open positions); guard flags (daily loss, floor, feed stale, reconcile, calendar, risk-off alarm); universe heat grid; decision trace; latest signal feed + toast |
| | **Market mood** (`#/command/mood`) | Opening + Sentiment + market context | morning brief (frozen 08:45); pre-open board (09:00–09:15 live); opening scorecard (from 09:15) and opening type (15:45); markets grid (GIFT Nifty, US, Europe, Asia, FX, crude, gold, bonds, India VIX, FII/DII); sentiment gauge with parts; risk-off banner; headlines timeline with tag chips; 60-day opening history |
| 02 Book | **Paper book** (`#/book`) | Swing book + Paper cycle + Live ₹ (locked) | cycle tiles (equity, cash, unrealised, net P&L, hit rate, costs split, cycle #); equity curve; open positions as R cards (Book B; Book A appears only if promoted); tomorrow's pending orders; closed trades with book/strategy filters and totals; taken vs skipped; rules in force; a locked "Live ₹" strip showing which gates are still open |
| | **Signals** (`#/book/signals`) | Signals + Intraday shadow + History | filter bar (date range, book, strategy, role pick/mirror/random, decision taken/skipped/shadow, symbol search); summary tiles; one table for every signal incl. Book A shadow with virtual outcome; "why refused" side panel in plain words; CSV export (this replaces the History archive) |
| 03 Evidence | **Evidence** (`#/evidence`) | Strategies + Accuracy + Research | gate table per trial (pass/fail chips, prereg link, trials counter); R histogram and win rate by strategy/month; paper-vs-backtest check; latest research reports with by-year, VIX tercile and results-season tables |
| 04 System | **Health** (`#/system`) | Go-live + Health + Data + Diagnostics | go-live verdict and gates; jobs (last run, result, next run); data coverage (lake, bhavcopy, corporate actions, pre-open capture days, missing days); feed/source states with age and errors; memory vs 600 MB; recent events |
| | **Settings** (`#/system/settings`) | Settings + Keys + Watchlist + API list | runtime settings (admin, whitelisted, every change logged); derived session times (read-only); universe and manual exclude/include; keys (encrypted, set / not set) with the **Test Angel (read-only)** button; API list link |

Retired as pages (still reachable as sections or filters): Overview, Opening, Sentiment, Watchlist, Swing book,
Paper cycle, Intraday (shadow), Live ₹, Session guard, Strategies, Accuracy, History, Research, Go-live, Data,
Diagnostics, Keys, API list. Old crypto-style addresses (`#/book/paper`, `#/command/signals`,
`#/system/golive`…) redirect to the page and section that now hold them.

Copy `crypto/tests/test_portal.py`'s structural checks: every native page has a view, every view names existing
widgets, every widget uses a defined Store key.

## 9. Phases and tickets

Each phase: branch `feat/v<N>-<topic>`, PR, `ruff check .` and `pytest -q` green, `docs/phase-reports/V<N>.md`.
Order: V0 → V1 → **V1b** → V2 → V3 → V4 → V6 → V7. **V5 (portal) can run in parallel with V1–V4** against the §7
fixtures. V1b goes early because pre-open and breadth history can't be downloaded later.

### V0: hygiene and safety (`feat/v0-hygiene`)

| Ticket | Work | Done when |
|---|---|---|
| V0-1 | Commit the current tree on `feat/mvp-backtest-news` (owner OK), fix the 2 ruff errors, open the MVP PR | CI green; `git status` clean |
| V0-2 | B24: default `web_host=127.0.0.1`; cookie `Secure` unless `cookie_secure=false`; `/keys` save refuses unless the request is HTTPS (`X-Forwarded-Proto: https`) or from 127.0.0.1 / Tailscale 100.64.0.0/10. Docs: nginx TLS or `tailscale serve` (owner picks, Q2) | tests: plain-HTTP public request to `/api/keys/save` gets 403; cookie has `Secure` |
| V0-3 | B25: replace `x or now()` with `x if x is not None else now()` everywhere | test at `now_ms=0` uses 0 |
| V0-4 | B9: `core/ticks.py` `round_to_tick(price, tick, "up"|"down"|"nearest")` with `config/tick_bands.json` fallback; every price sent to a broker goes through it. Buy limits round up, sell limits round down, stop triggers round toward the market | tests: 1234.56 on a ₹0.10 tick → 1234.60 up / 1234.50 down; 249.99 uses ₹0.01; OrderManager emits only on-tick prices |
| V0-6 | Keys page: **"Test Angel (read-only)"** button → `POST /api/keys/test-angel` (admin): login, `rmsLimit`, `allholding`, `position`, logout; returns status, error code with a plain-English hint (AB1050 → "TOTP secret doesn't match this client code: re-enable TOTP and save the new secret"), available cash, holdings count and value. Never returns tokens; masks the client code; rate-limited to 1 call per 2 minutes (avoid lockouts) | fake-SmartConnect tests for OK, AB1050, network error; a second call within 2 min gets 429 |
| V0-7 | Upgrade `smartapi-python` from the pinned **1.4.1** (old base URL `apiconnect.angelbroking.com`) to **1.5.5** (Feb 2025, base URL `apiconnect.angelone.in`, matches Angel's current docs). `generateSession(client_code, PIN, pyotp.TOTP(secret).now())` per the official README. **Send the real IP headers**: the 1.4.1 SDK falls back to a hard-coded `X-ClientPublicIP: 106.193.147.98` and `X-ClientLocalIP: 127.0.0.1` (seen on the server 23 Oct 2026); set `X-ClientPublicIP` = the registered static IP (checked against `expected_static_ip`), `X-ClientLocalIP` = the machine's private IP, `X-MACAddress` = its MAC. Re-record the login fixture | fake-server login test passes on 1.5.5 and asserts the three IP/MAC headers; `scripts/login_check.py` prints 4 OK lines on the server (owner runs) |
| V0-8 | **Keys page: see what is saved** (owner, 23 Oct 2026: "give option to see old values on keys page"). (a) Every row always shows a **masked preview** (first 2 + `•••` + last 2; MPIN shows `••••` only), length, saved time, source (DB / .env) and a 12-char **keyed** fingerprint (HMAC-SHA256 with `SECRETS_MASTER_KEY`, so it can't be reversed by guessing). **No fingerprint for the MPIN or any value under 8 characters**: a plain hash of a 4-digit PIN is reversed by trying all 10,000 PINs (lesson from 23 Oct 2026); check those with Compare only. (b) **Compare**: type a value → `POST /api/keys/compare {key, value}` → "matches the saved value" / "differs" (+ which position first differs, e.g. "character 5"); nothing is returned but the verdict. (c) **Reveal** (eye button): `POST /api/keys/reveal {key, password}` needs the admin cookie **and** the admin password typed again; returns the current value once with `Cache-Control: no-store`; the page shows it for 30 s with a copy button, then hides it; writes event `key_revealed` (key name only); max 5 reveals per 10 min. (d) **History**: new table `app_settings_history(key, fingerprint, masked, saved_at, saved_by)` (keyed fingerprint; none for short values) appended on every save/clear; the page lists the last 5 versions per key, masked + fingerprint + time. Old plaintext is never kept (a replaced secret is gone by design). Compare and reveal only work over HTTPS, Tailscale or localhost (same rule as save, V0-2); on plain HTTP they're greyed with "needs a secure connection" | tests: masked preview for each kind; compare true/false + first differing position; reveal 401 without cookie, 403 with a wrong password, 403 over plain HTTP from the internet, 429 on the 6th reveal; history row on every save; no value in any log line or event |
| V0-9 | **TOTP from UTC, never local time** (23 Oct 2026 incident: a process that changed `TZ` after start generated a wrong first TOTP, so every login got AB1050). `scripts/login_check.py` and `web/test_angel.py` (and any future login) use `pyotp.TOTP(secret).at(datetime.now(timezone.utc))` instead of `.now()`; normalise the secret (strip spaces, upper-case) and refuse anything that isn't base32 or is under 16 characters (the 6-digit code mistake) | test: set `os.environ['TZ']` to Asia/Kolkata mid-test and the code still equals `HOTP(secret).at(epoch // 30)`; a 6-digit 'secret' is rejected |
| V0-5 | B23: one path source. Every script defaults `--db`/`--lake` from `settings.data_dir`. Move the lake to `var/lake/` (keep `data/` as the Python package only) | test: research and portal resolve the same db path |

### V1: market layer (`feat/v1-market`)

| Ticket | Work | Done when |
|---|---|---|
| V1-1 | B16: `config/sessions.json` with dated regimes (MARKET_INDIA §2): `{from, to, class: "fo"|"non_fo", pre_open: [...phases], continuous: ["09:15", end], cas: {...}|null, post_close: ["15:50","16:00"]}`. `session_state(ms, stock_class)` returns PRE_OPEN, OPEN, NO_NEW_ENTRIES, SQUARE_OFF, CLOSING_AUCTION, POST_CLOSE, CLOSED, HOLIDAY, SPECIAL | tests: F&O stock 23 Oct 2026 15:20 → CLOSING_AUCTION; same time 8 Dec 2026 → OPEN; non-F&O 23 Oct 15:20 → OPEN; 09:09 → PRE_OPEN; Muhurat 8 Nov 14:30 → SPECIAL/OPEN |
| V1-2 | B17/B18: Muhurat 2026 per NSE (afternoon; owner verifies Q4). Calendar loads every `holidays_*.json`; asking about a year without a file raises `CalendarMissing`; health turns red; all trading jobs skip with an alert. Every cron job checks `is_trading_day` first. Muhurat: no new entries in either book (setting `trade_special_sessions=false`) | tests: 2027-01-04 raises without a 2027 file; a 2026 holiday skips jobs; Muhurat window correct |
| V1-3 | B19/D4: derive `square_off_at` / `no_entry_after` from `broker_squareoff_at` and the leads. Book A shadow uses the same times | tests: broker 15:10 → engine 14:55 / 14:35; invariant test |
| V1-4 | B20 + D3: refresh `costs_angel.json` (MARKET_INDIA §5) with `source_url`, `as_of`, `verified_against_contract_note: false`; `order_brokerage` = max(min ₹5, min(₹20, 0.1%)); risk enforces `min_position_cnc_inr` with reason `below_min_cnc_position` | tests: the round-trip table in MARKET_INDIA §5 to the paisa; ₹3,000 order → ₹5 brokerage |
| V1-5 | Instruments: daily scrip master → `tick_size`, `is_fo` (symbol has NFO futures), series EQ only; `config/surveillance.json` (ASM/GSM) with risk reason `surveillance`; B26 exposure includes the new position | fixture tests; a surveillance-listed symbol is skipped with the reason |
| V1-6 | Survivorship: `config/universe_history.csv` (date, symbol, action add/remove) + `universe_on(date)`; lab uses it | test: a symbol removed in 2020 is tradable in 2019 and not in 2021 |
| V1-7 | B21: UDiFF bhavcopy parser (check exact headers against one real file the owner downloads; commit a 5-row fixture), legacy parser for old dates, delivery file, `data/corporate_actions.py` (split/bonus factors from NSE corporate actions; the owner provides an export for the fixture). The lake stores raw OHLC plus `adj_factor`; strategies read adjusted prices; costs use raw prices | tests: both bhav formats; a 1:1 bonus fixture gives no −50% gap in adjusted closes |
| V1-8 | `data/events.py`: results dates (NSE board-meeting / financial-results announcements), F&O expiry = last Tuesday of the month (moved back if a holiday), RBI MPC dates (config), Budget day. Features on every signal: `results_in_days`, `expiry_day`, `mpc_day` | tests: expiry-day rule on 2026 months incl. a holiday Tuesday |

### V1b: opening and sentiment recorder (`feat/v1b-opening`), D8

Daily timeline (IST): 06:00–23:30 global cues every 5 min · 08:30 overnight headlines scored · **08:45 morning
brief frozen** (Telegram) · 09:00–09:15 pre-open snapshots every 30 s · 09:15–09:45 opening scorecard every
minute · 09:20 Telegram opening summary · 15:45 opening type and open-to-close written · 18:00–20:00 FII/DII
provisional · every 15 min (08:00–23:30) headlines fetched, tagged and scored.

| Ticket | Work | Done when |
|---|---|---|
| V1b-1 | `data/global_cues.py`: instrument map in `config/cues.json` (key, label, region, source symbol: Yahoo `^GSPC`, `^IXIC`, `^DJI`, `ES=F`, `NQ=F`, `^GDAXI`, `^FTSE`, `^FCHI`, `^STOXX50E`, `^N225`, `^HSI`, `^KS11`, `INR=X`, `DX-Y.NYB`, `BZ=F`, `GC=F`, `^TNX`, `^NSEI`, `^INDIAVIX`; GIFT Nifty via `gift_nifty_source`). Each row stores its own previous close and a `stale` flag (market closed, or no update for 2× its interval). `data/flows.py`: NSE FII/DII provisional (browser-like session; unofficial) | fixture tests per source; a closed market is marked stale, not 0% |
| V1b-2 | `data/preopen.py`: NSE pre-open JSON (`key=NIFTY` and `key=FO`) every `preopen_snapshot_s` from 09:00 to 09:15; the final snapshot is marked `final=1`; the Nifty IEP too. If NSE blocks the request, try Angel's quote during pre-open (VERIFY), else log `preopen_unavailable` | fixture test; a missing day shows on Data health |
| V1b-3 | News: real scheduled fetch (Moneycontrol, ET Markets, Business Standard, Reuters India, NSE announcements RSS where available), `published_ms` from the feed, dedupe by `external_id` and near-duplicate title; new tags (MARKET_INDIA §8b); rules-only scoring on the server (FinBERT via the HF Space optional, same as crypto); `headlines` table; each headline later gets `nifty_move_next_60m` | tag tests for each new event type; dedupe test |
| V1b-4 | `engine/opening.py`: build and freeze the morning brief at 08:45; opening scorecard; opening type at 15:45 (rules: gap ≥ +0.5% & close > open = gap-up-and-go; gap ≥ +0.5% & close < open = gap-up-fade; mirror for gap-down; else flat); `sentiment_daily` composite (reuse `news/sentiment.composite_score`, parts stored separately); risk-off alarm rule + one Telegram alert per day | tests: each opening type on a hand-built day; alarm fires only when all three conditions hold within the window |
| V1b-5 | Endpoints `/api/opening`, `/api/sentiment`, `/api/headlines` (§7) and the Market mood page (§8) (if V5 isn't merged yet: JSON + a temporary page) | contract tests; owner sees the morning brief on the phone at 08:45 |
| V1b-6 | Research hook: every Book A/B signal gets the day's `gap_pct`, `imbalance`, `composite`, `open_type_so_far` and `risk_off_alarm` as features (no lookahead: only values known at decision time) | test: a 10:00 signal never sees the 15:45 opening type |

### V2: backtester correctness (`feat/v2-lab-fixes`)

Write each bug as a failing test first. The probes in §3.3 are the test cases.

| Ticket | Work | Done when |
|---|---|---|
| V2-1 | B3/B4: daily fills. Entry is the next day's LIMIT at close × 1.005, filled only if that day's low ≤ limit, at min(open, limit) + slippage; else `no_fill`. Stop: if open ≤ stop, fill at open − slippage, else at stop − slippage (− extra 0.05% for stops, as PLAN A9.5). Trail = highest close since entry − 2.5×ATR14, never lowered. Time exit after 20 sessions at the close. Entry day: the stop applies from the open (conservative). `entry_ms` = fill day 09:15 IST | tests: gap-down probe → R ≈ −10.6; gap-up over the limit → no_fill; trail never lowers |
| V2-2 | B1/B2/B14/B15: intraday. Resample 1m → strategy timeframe before calling the strategy. Build the context every day (`prev_close`, `pdh`, `gap_pct`, `slot_vol_avg` from 20 prior days, cross-sectional `ret_decile`/`rs_rank` across the universe at the decision minute). Stops for both sides; targets; time exit at the engine square-off; one trade per strategy, symbol and day | tests: the short probe stops at 103.2 ± slippage; ORB target 2R hit; square-off at 14:55 (V1-3 times); S3/S4/S5 each fire on a hand-built day |
| V2-3 | B13: BarView knows the timeframe. A bar is closed at open + timeframe; a daily bar closes at the session's close for its class and date (V1-1). Asking for an unclosed bar raises `LookaheadError` | tests: daily bar not visible at 14:00 the same day; visible at 16:00 |
| V2-4 | B5: `lab/baselines.py` simulates real mirror trades (opposite side, same stop % and target R, same exit engine) and random-time trades (deterministic seed, same day/symbol window, same side, stop % and exits; daily: a random day within ±10 sessions). Delete the fabricated baselines in `scripts/research.py` | test: on a strategy with planted edge, pick > mirror and > random; on shuffled outcomes the gate fails |
| V2-5 | B6: portfolio backtest over `universe_on(date)` with shared cash, `max_open_swing`, one position per symbol, priority when several signals fire the same day (crypto `swing_book.priority`: strongest strategy first, then lower ATR%), costs per trade | tests: two simultaneous signals with 1 free slot → the priority one taken, the other logged `max_open_swing`; deterministic |
| V2-6 | Evaluate: halves by date, by year, by India VIX tercile, by results season, cost stress ×1.5; ledger stores `prereg_id`, `data_hash`, `post_hoc` columns | tests: same inputs → same report hash; trials count increments |
| V2-7 | D6: `core/exits.py` with `fill_entry(order, bar)`, `step_exits(position, bar, rules) -> (position, exit|None)`, `virtual_outcome(signal, bars, rules)`. `lab/backtest.py`, the paper engine (V4) and the outcome job (V4-4) all call it | test: backtest trade == paper trade == virtual outcome for the same signal and bars |

### V3: real data and the research run (`feat/v3-research`)

| Ticket | Work | Done when |
|---|---|---|
| V3-1 | Backfill real bhavcopy 2012-01 → today (owner runs the downloader; throttled, resumable), apply corporate actions, data-health report. Delete the synthetic lake | `docs/phase-reports/V3.md` lists symbols, first/last date, missing days (0 on trading days), corporate actions applied |
| V3-2 | Write `docs/PREREG.md` **before** running: S6_swing, S6b_keltner (PLAN A10 as written, now with correct fills); F1 = S6 + Nifty 30-day vol rank > 0.667 skip (crypto filter port); F2 = S6 + skip when Nifty < 200-day SMA; S7_xsmom (first trading day of each month: rank `universe_on(date)` by the mean of z-scores of 6m and 12m return ÷ daily-return volatility, like Nifty200 Momentum 30; hold the top N = floor(capital / min_position_cnc_inr); exit when a holding falls out of the top 2N at a rebalance or at a 3×ATR20 safety stop). 5 trials total, halves 2012–2018 / 2019–2026 | PREREG committed in a commit **before** the run commit |
| V3-3 | Run all five through the lab (V2), Book B gate (n ≥ 100 per half, avg R ≥ +0.10 both halves, beats mirror and random both halves, R > 0 under cost stress ×1.5). Book A only on whatever 1m depth exists (likely none) | `V3.md` with the gate table, by year, VIX tercile, results season, cost in R at ₹1L capital, and a plain-English verdict per trial; ledger count shown |

The owner then picks which passed trials (if any) go to paper. "None passed" is a valid outcome. Then the paper
engine still runs S6 **as a shadow book** to collect live evidence (same as crypto kept logging).

### V4: paper engine, Book B end-of-day (`feat/v4-paper`)

Daily timeline (trading days only, IST, times from `sessions.json`):

| Time | Job | What it does |
|---|---|---|
| 08:30 | `job_instruments` | scrip master, ticks, F&O flags, surveillance list, today's session regime |
| 08:45 | `job_login` | Angel login (data only while paper); on failure the paper engine still runs on bhavcopy |
| 09:00 | `job_pending` | move `pending_orders` for today into the PaperBroker as DAY LIMIT orders |
| 09:15–15:30 | `job_mark` every 5 min | Angel LTP (Yahoo fallback) → unrealised P&L for display only. **Never used for fills** |
| 16:15 | `job_eod_fill` | today's daily bar per symbol (Angel ONE_DAY after CAS + post-close): fill pending entries by `core/exits.fill_entry`; step every open position by `step_exits`; book costs; close trades; update the cycle wallet |
| 16:20 | `job_scan` | run enabled Book B strategies on today's closed daily bars; risk; write signals (pick + mirror + random); for picks that pass, write `pending_orders` for the next trading day |
| 16:30 | `job_outcomes` | `virtual_outcome` for every unresolved signal (taken, skipped, mirror, random) |
| 16:35 | `job_eod_report` | `daily_pnl`, Telegram summary |
| 18:30 | `job_bhav_check` | bhavcopy arrives; re-check today's bars; any difference to the Angel bar > 1 tick → parity event (bhavcopy is truth for research) |
| 18:45 | `job_backup` | as PLAN A14.2 |

| Ticket | Work | Done when |
|---|---|---|
| V4-1 | Migration 002 (§5); repository functions | migrate twice is a no-op; insert/read each new table |
| V4-2 | `data/quotes.py`: Angel LTP poller (batched, throttled) with Yahoo fallback; writes the quotes cache used by the tape and `job_mark` | fake-client tests; the fallback is used when Angel is unavailable |
| V4-3 | B7: PaperBroker accounting. `cash` += realised P&L − costs; CNC buy needs cash ≥ value + estimated costs (else REJECTED `insufficient_funds`); CNC sell only from holdings (no short); holdings bought today can't be sold today; MIS margin = 20% of value, released with P&L. Equity = cash + Σ holdings × mark | tests: the +₹10k probe ends at ₹1,10,000 − costs; CNC short rejected; same-day CNC sell rejected |
| V4-4 | `engine/outcomes.py` + `job_outcomes`; take vs skip scoreboard (crypto `regime_gate.signal_scoreboard`) | tests: skipped signal resolves to the same R the trade would have had |
| V4-5 | B8/B10/B11/B12: Broker protocol (sync, dataclasses) implemented by PaperBroker and an Angel adapter; OrderManager looks up the tag before sending (real idempotency); watchdog tracks `crossed_since_ms` per bracket and fires only after `stop_watchdog_s` continuous crossing; `square_off` sends a protected LIMIT exit | tests per PLAN A15 orders list, incl. the watchdog probe now **not** firing on the first tick |
| V4-6 | `engine/paper_engine.py` + runner wiring for the timeline above; cycle start on first enable; cycle ends on target / floor; kill switch stops new entries only | an end-to-end test replays 30 fixture days through the jobs and gets the same trades as `lab/backtest.py` on those bars (parity = 0 differences) |
| V4-7 | Telegram: entry, exit, rejection, daily summary (PLAN A13.3 wording), quiet hours | fake Telegram tests |
| V4-8 | Parity job (PLAN A12.2) on the paper book: replay today vs paper trades | parity page shows 0 faults on the e2e fixture |

### V5: portal parity with crypto (`feat/v5-portal`, can start after V0)

| Ticket | Work | Done when |
|---|---|---|
| V5-1 | Copy crypto `scheduler/portal/{core.js, portal.css, portal.html, nav.js, chrome.js, chrome.css}` into `web/portal/`; adapt to hash routing under `<base href="/nse/">`, the NSE nav (§8) and versioned assets (`?v=<hash>`, long cache) | the shell loads at `/nse/`; four palettes switch and persist |
| V5-2 | Endpoints in §7 (`web/portal_api.py`), backed by real tables when present and **empty states** when not; `web/reasons.py` | contract tests: each endpoint matches its fixture's keys |
| V5-3 | Command hub: Today and Market mood (§8) | widget/view/store structural test passes |
| V5-4 | Book hub: Paper book and Signals | same, plus a test that no widget renders demo numbers when the store is empty |
| V5-5 | Evidence, Health and Settings (Go-live gates computed server-side in `/api/golive`) | same |
| V5-6 | Phone check: each page at 375 px wide, no horizontal scroll; `prefers-reduced-motion` honoured | owner checks on the phone (PLAN A1 working style) |

### V6: Book A shadow on the live feed (`feat/v6-intraday-shadow`)

| Ticket | Work | Done when |
|---|---|---|
| V6-1 | `data/stream.py`: real Angel WebSocket V2 thread, SnapQuote, reconnect/backoff, resubscribe, ticks → asyncio queue (PLAN P1-5) | fake-WS reconnect test |
| V6-2 | `data/bars.py`: implement the late-tick rule (it's a `pass` today), F&O stocks' last bar 15:14 while CAS runs; record `bars_1m` and `spread_1m` | late / out-of-order / missing-minute tests |
| V6-3 | Book A strategies on live bars → signals with role and decision `shadow` → `virtual_outcome` with MIS costs at the engine square-off. No paper trades while `book_a_mode=shadow` | a recorded fixture day produces the same shadow signals as the backtest on the same bars |
| V6-4 | Angel 1m history depth report (PLAN P1-3). The paid-feed decision stays with the owner | report per symbol |

### V7: live readiness (former P5; `feat/v7-live`), THIS PHASE CAN SEND REAL ORDERS

As PLAN A16-P5, plus: Angel adapter sends LIMIT / STOPLOSS_LIMIT only (no MARKET, no IOC: Angel prohibits them
for algos); static-IP check before the first order of the day; the IP can change at most once a week, so
moving servers is planned ahead; CAS-aware cut-offs; contract-note reconciliation of costs (paper model within
+0.03%); CNC stop orders re-placed every morning (DAY orders expire); tax export by category (MARKET_INDIA §7).
Nothing merges without the owner's written yes.

## 10. Prompts to paste into Cursor (one chat per phase)

```
[V0] Read AGENTS.md, docs/PLAN_V2.md (§3, §6, §9-V0) and docs/MARKET_INDIA.md §4. Branch feat/v0-hygiene from
feat/mvp-backtest-news after the owner has committed it. Implement V0-1..V0-5 exactly. Write the failing test
first for each ticket. Never change mode/live_orders defaults. ruff + pytest green, docs/phase-reports/V0.md, PR.

[V1] Read AGENTS.md, docs/PLAN_V2.md (§3.3 B16-B21, B26, §4, §6, §9-V1) and docs/MARKET_INDIA.md fully. Branch
feat/v1-market. Implement V1-1..V1-8. Session times, holidays, ticks and costs are data files with dates and
sources, never constants in code. Use the test cases written in each ticket. Where MARKET_INDIA says VERIFY,
keep the value configurable and list it in V1.md under "owner to verify". PR.

[V1b] Read AGENTS.md, docs/PLAN_V2.md (§2 D8, §5 opening tables, §6, §7 opening/sentiment/headlines, §8
Opening + Sentiment pages, §9-V1b) and docs/MARKET_INDIA.md §8b. Branch feat/v1b-opening. Build the recorder:
global cues, FII/DII, pre-open snapshots, scheduled tagged headlines, morning brief, opening scorecard, opening
type, sentiment composite, risk-off alarm. It is recording + display only: nothing here may block, size or
time a trade. Every source has a fixture test and a stale flag. No network in tests. PR.

[V2] Read AGENTS.md, docs/PLAN_V2.md (§3.3 B1-B6, B13-B15, §9-V2) and docs/PLAN.md A10-A11. Branch
feat/v2-lab-fixes. First add the probe cases from §3.3 as failing tests, then fix. Build core/exits.py and make
lab/backtest.py use it. Do not change any strategy parameter (pre-registered); if a rule is ambiguous, ask.
Delete the fabricated baselines. PR with before/after numbers on the synthetic fixture only.

[V3] Read AGENTS.md, docs/PLAN_V2.md (§9-V3) and docs/MARKET_INDIA.md §9-10. Branch feat/v3-research. Write
docs/PREREG.md and commit it before any run. I (owner) run the bhavcopy backfill on my machine with the command
you give me. Run the five trials, count every run in the ledger, write docs/phase-reports/V3.md with the gate
table and a plain-English verdict. No parameter changes after seeing results (a change = new post-hoc trial).

[V4] Read AGENTS.md, docs/PLAN_V2.md (§2, §5, §7, §9-V4) and docs/PLAN.md A9, A12. Branch feat/v4-paper. Build
the Book B end-of-day paper engine with the timeline in V4. Paper must equal the backtest on the same bars
(V4-6 e2e test). Fix PaperBroker accounting first (B7). No live orders anywhere. PR.

[V5] Read AGENTS.md, docs/PLAN_V2.md (§7, §8, §9-V5) and the crypto repo's docs/PORTAL_REVAMP.md plus
scheduler/portal/ at /Users/dhruv/personal/Tennis-bet/crypto-signal-engine. Branch feat/v5-portal. Port the
micro-UI and build every page in §8 against the §7 endpoints (fixtures first). Nothing simulated on the real
portal; empty states instead. Port crypto's structural portal tests. PR with phone screenshots.

[V6] Read AGENTS.md, docs/PLAN_V2.md (§9-V6), docs/PLAN.md A8, P1-5..P1-7. Branch feat/v6-intraday-shadow.
Real Angel WebSocket, bar recording, Book A in shadow only. PR.

[V7] Read AGENTS.md, docs/PLAN.md A3, A8, A9.4, A12.3, A14, A16-P5 and docs/PLAN_V2.md §9-V7. Branch
feat/v7-live. THIS PHASE CAN SEND REAL ORDERS: put the warning in capitals at the top of the PR. Implement
behind mode=live AND live_orders=true. Do not set either flag anywhere.
```

## 11. Questions for the owner (Cursor uses the default until answered)

| # | Question | Default |
|---|---|---|
| Q1 | What is Angel's MIS auto square-off time for F&O stocks right now? (Angel app → order screen, or support) | 15:10 → engine square-off 14:55, no entries after 14:35 |
| Q2 | Portal access: keep public `http://52.62.37.4/nse/`, or move to Tailscale (PLAN A13) / add HTTPS? | Tailscale; `/keys` refuses plain HTTP from the internet |
| Q3 | Book A shadow-only until it passes the gate (like crypto intraday)? | Yes |
| Q4 | Verify Muhurat 2026 (8 Nov) timings in the NSE circular. Should either book trade it? | 14:20–15:15 continuous; no new entries in either book |
| Q5 | Paper capital ₹1,00,000 and min CNC position ₹20,000? | Yes |
| Q6 | Approve the 5 pre-registered Book B trials (S6, S6b, F1, F2, S7)? | Yes |
| Q7 | Paper cycle target wallet (crypto uses a target)? | None, open-ended |
| Q8 | Commit the current untracked tree to `feat/mvp-backtest-news` and open the MVP PR? | Yes |
| Q9 | Share the first contract note (masked) so costs can be marked verified? | Pending |
| Q10 | Download one UDiFF bhavcopy and one NSE corporate-actions export for fixtures? | Pending |
| Q11 | GIFT Nifty data: no reliable free API. Pay for a feed, or use US futures + Asia as the proxy? | Proxy until decided |
| Q12 | OK to read NSE website JSON (pre-open, FII/DII) with a browser-like session? It's unofficial and can break | Yes, with a stale flag and alerts |
| Q13 | RESOLVED 23 Oct 19:3x IST: the AB1050 came from a TZ bug in Claude's test script, not the keys (see DECISIONS). Was: Angel login fails with AB1050 "Invalid totp and client combination" (23 Oct 17:10 IST). Please re-enable TOTP on smartapi.angelone.in for this client code, save the new secret on `/keys`, then rerun the read-only check | Blocking anything that needs Angel |

## 12. Risks specific to this plan

1. **Session rules keep changing** (CAS on 3 Aug, revised for 7 Dec 2026, unfilled-order rules on 8 Feb 2027).
   Mitigation: dated `sessions.json`, a health check that fails when today falls outside every regime.
2. **Corporate-action data quality.** A missed bonus fakes a crash. Mitigation: a gap > 15% on a Nifty 100 stock
   with no action recorded raises a data-health alert and excludes that day from research.
3. **Small Book B sample.** Daily breakouts on 100 stocks give maybe 100–300 trades per half. Mitigation: the
   n ≥ 100 rule, plus "no" is an accepted answer.
4. **Momentum crashes** (−30% in Sep 2024–Mar 2025 for the momentum index). Mitigation: report the worst
   3-month window and the worst year in V3, not just the average.
5. **Paper EOD fills are optimistic about queue position** at the limit price. Mitigation: a fill needs the day's
   low to be at least one tick **below** the limit (not just equal), and slippage applies.
6. **Copying the crypto UI brings its complexity.** Mitigation: port only the pages in §8; no AI pages until news
   or AI proves lift.
