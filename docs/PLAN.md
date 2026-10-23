# Trading Systems Plan

Part A: NSE Equity Engine (new project, Angel One SmartAPI): full build spec for Cursor  
Part B: Machine Learning + RAG memory for the existing Crypto Signal Engine

Owner| Dhruv Parekh (GitHub `dhruvparekhdp`), Mumbai  
---|---  
Written| 23 Oct 2026, by Claude (reviewer) for Cursor (builder)  
How to use| Cursor starts every new chat by reading this whole document (or `docs/PLAN.md` in the repo, which is this document as Markdown). It has no other context. Every decision is written down here; when something is unclear, Cursor asks the owner instead of guessing, and logs the answer in `docs/DECISIONS.md`.  
Workflow| Cursor builds one phase per branch, then opens a PR. Claude reviews the PR against this plan. The owner approves and merges. Nothing goes live without the owner's explicit written yes.  
  
### Contents

  1. A1 Purpose, owner and working rules
  2. A2 The numbers that shape the design (costs, base rates, sizing)
  3. A3 Rules from SEBI and Angel One
  4. A4 Architecture and decisions table
  5. A5 Repository layout (every file)
  6. A6 Configuration (every setting)
  7. A7 Data model (SQLite tables, Parquet lake)
  8. A8 Angel One SmartAPI integration
  9. A9 Core modules: clock, costs, risk, orders, paper broker
  10. A10 Strategies (pre-registered rules)
  11. A11 Backtester and research lab
  12. A12 Engine runtime: schedule, jobs, safety
  13. A13 Portal, API and Telegram
  14. A14 Deployment, server, backups, security
  15. A15 Testing standards
  16. A16 Phases and tickets (P0 to P6) with acceptance criteria
  17. A17 AGENTS.md (verbatim) and the Cursor prompt for each phase
  18. A18 Risks and disadvantages
  19. A19 Owner checklist, and how to test the Angel API key
  20. Part B: ML + RAG plan for the crypto engine



## A1. Purpose, owner and working rules

**Goal.** A new, separate project that trades Indian equities (NSE cash market, Nifty 100 stocks) using Angel One's SmartAPI. **Intraday first** , in MIS (intraday) product. It also has a delivery swing book (CNC) because the numbers in A2 show that is where costs are lowest. Futures and options are **out of scope** (owner: they need too much margin). Everything starts on **paper** and only goes live after the evidence gates in A16 pass and the owner says yes in writing.

**Owner's decisions (23 Oct 2026):** broker Angel One SmartAPI; live capital later ₹25k-₹1 lakh; universe Nifty 100; new private GitHub repo; runs as a second service on the owner's existing AWS EC2 server (t3.small, 2 GB RAM, Sydney region ap-southeast-2, which already runs the crypto engine).

**How the owner likes to work.**

  * Phase by phase, with the owner's OK at each gate.
  * Plain English everywhere: code comments, pages and alerts.
  * Pages that work on a phone, with charts and the ability to drill down to every record.
  * Honest numbers, never cherry-picked.
  * A test with every change.
  * No secrets in git, ever.



**Lessons carried over from the owner's crypto engine (these are requirements, not suggestions):**

  1. **Costs decide intraday.** In crypto, intraday signals had a gross edge of about +0.05R and costs of 0.32R, which is a guaranteed loss. Every result in this project is **after costs** , at the position size we would really trade.
  2. **Use mirror controls.** Every strategy's trade also gets a "mirror" (the same entry on the opposite side) and a random-time baseline. A strategy only counts if it beats both. Otherwise one market-wide move looks like skill.
  3. **Pre-register and use two periods.** Rules are written down before testing. They must pass in **both** halves of history. Every attempt is counted in a ledger, so "we tried 50 things and kept the lucky one" is visible.
  4. **Paper mirrors live.** The paper broker uses exactly the live code path, risk rules and costs. A daily **parity check** compares paper or live results against a replay of the same day.
  5. **Use safety rails.** Kill switch, daily loss limit, capital floor, maximum open positions, a spread/depth guard before entries, and stops placed at the exchange (not only in our memory).
  6. **The lifecycle is paper, then small live, then scale.** The swing book was the only proven edge in crypto. Most intraday ideas failed. Expect the same here and treat it as a valid outcome.



## A2. The numbers that shape the design

### A2.1 Cost of one round trip at Angel One (all rates are settings, see A6)

**Rates disagree between sources in Oct 2026.** P2 must confirm each rate against Angel One's brokerage calculator, using screenshots the owner provides, and store the source URL and date in `config/costs_angel.json`. The defaults below are a best estimate.

Charge| Intraday (MIS)| Delivery (CNC)  
---|---|---  
Brokerage| min(₹20, 0.1% of order value) per executed order| min(₹20, 0.1%) per order (Angel has advertised ₹0 at times, so verify)  
STT| 0.025% of sell value| 0.1% of buy value + 0.1% of sell value  
Exchange transaction (NSE)| 0.00297% of each side's value| 0.00297% each side  
SEBI fee| ₹10 per crore (0.0001%) each side| same  
Stamp duty| 0.003% of buy value| 0.015% of buy value  
GST| 18% of (brokerage + exchange + SEBI)| same  
DP charge| none| about ₹20 + 18% GST per stock per sell day  
Slippage (our model)| 0.03% per side for Nifty 100 with marketable limit orders| 0.05% per side  
  
**Worked examples, intraday, round trip (buy then sell the same value P):**

Position P| Brokerage| STT| Exch.| SEBI| Stamp| GST| Total| % of P| \+ slippage 0.06%| In R at 0.5% stop| In R at 1% stop  
---|---|---|---|---|---|---|---|---|---|---|---  
₹25,000| 40.00| 6.25| 1.49| 0.05| 0.75| 7.48| ₹56.0| 0.224%| 0.284%| **0.57R**|  0.28R  
₹50,000| 40.00| 12.50| 2.97| 0.10| 1.50| 7.75| ₹64.8| 0.130%| 0.190%| 0.38R| 0.19R  
₹1,00,000| 40.00| 25.00| 5.94| 0.20| 3.00| 8.31| ₹82.5| 0.082%| 0.142%| 0.28R| **0.14R**  
₹2,00,000| 40.00| 50.00| 11.88| 0.40| 6.00| 9.41| ₹117.7| 0.059%| 0.119%| 0.24R| 0.12R  
  
**Delivery example:** ₹50,000 round trip comes to brokerage 40 + STT 100 + stamp 7.50 + exch 2.97 + SEBI 0.10 + DP 23.60 + GST 7.75 = **₹181.9 (0.36%)**. Add 0.10% slippage and the total is 0.46%. At a typical swing stop of 5%, that is only **0.09R**.

**Conclusions that are now requirements:**

  * Intraday positions must be **at least ₹1,00,000 in value** (MIS margin makes that affordable on ₹25-50k of capital) with stops of 0.8-1.5%. Below that, costs eat 0.3-0.6R per trade. The risk module enforces `min_position_inr`.
  * Delivery swing costs about 3-6x less per unit of risk. So the project runs **Book A (intraday MIS)** and **Book B (delivery swing CNC)** , both on paper, and the evidence decides which goes live first.
  * A strategy must clear **+0.10R per trade after costs** in both halves of history. Expect a gross edge of at least +0.25R to get there.



### A2.2 Base rates (what to expect)

  * SEBI study (July 2023, FY 2022-23): about **7 in 10 individual intraday traders** in the equity cash segment lost money. Trading costs were a big share of the losses. Default expectation: an intraday rule has **no edge after costs** until proven otherwise.
  * Owner's crypto results: intraday direction was a coin flip (walk-forward AUC 0.52). The swing book (multi-day breakouts) made +0.35R per trade over 5 years. Filters and AI judgement never improved it.



### A2.3 Sizing at the owner's capital

Capital| Risk/trade (1%)| Stop| Position| MIS margin (~20%)| Cost in R| Verdict  
---|---|---|---|---|---|---  
₹25,000| ₹250| 0.5%| ₹50,000| ₹10,000| 0.38R| too costly for intraday; fine for Book B  
₹50,000| ₹500| 0.5%| ₹1,00,000| ₹20,000| 0.28R| borderline  
₹50,000| ₹500| 1.0%| ₹50,000| ₹10,000| 0.19R| borderline  
₹1,00,000| ₹1,000| 1.0%| ₹1,00,000| ₹20,000| 0.14R| workable  
  
So Book A should go live with **₹50k or more** , and Book B can start at ₹25k.

### A2.4 Data limits

  * Angel's historical candle API returns 1-minute bars for at most about **30 days per request** (larger windows for coarser intervals). Users report a **500-row cap** and throttling (error AB1021). Years of free 1-minute history may therefore not exist. P1 measures the real depth.
  * Free official daily data: **NSE bhavcopy** (daily OHLC, volume, delivery quantity) back to the 1990s. It is enough for Book B research.
  * The engine **records its own 1-minute bars from the live websocket from day one**. That builds intraday history that no API can take away.
  * If Angel's 1-minute history is under 1 year, intraday research needs either months of our own recording or a paid feed (TrueData / Global Datafeeds, roughly ₹1-2k/month). That is the owner's decision at the end of P1.



## A3. Rules from SEBI and Angel One

SEBI's retail algo-trading framework took effect on **1 April 2026** (per broker notices; Cursor must not rely on details beyond this list without checking Angel's current docs):

  * **Static IP:** orders are accepted only from the static IP registered on the SmartAPI app. Orders from other IPs are rejected. Our IP is an **AWS Elastic IP** on the EC2 server. Data and login calls may work from other IPs; order calls will not.
  * **Daily login (2FA):** a session lasts one trading day. No long-lived refresh tokens. The engine logs in every morning with client code, 4-digit MPIN and a TOTP code generated from the TOTP secret (`pyotp`).
  * **Order rate:** at most 10 orders per second, including modifications and cancels. We throttle to **5 per second**.
  * **Market orders** are converted to market-price-protection (MPP) orders. We use **limit orders** and stop-limit orders only (A9.4).
  * **Algo-ID:** exchange tagging of algo orders is handled by the broker for personal API use below the threshold. Verify with Angel support in P5.
  * **Fallback if automatic TOTP is ever disallowed:** at 08:45 IST the engine sends a Telegram message asking the owner for the 6-digit code and logs in with the reply (A13.3).



**SmartAPI app registration (done by the owner on smartapi.angelone.in, "Add App"):**

  * App Name `nse-intraday-engine`
  * Redirect URL `https://dhruvparekh.in` (not used by TOTP login)
  * Post back URL empty
  * Primary Static IP = the EC2's Elastic IP
  * Secondary empty



Also enable TOTP on the SmartAPI site. Brokers limit how often the IP can be changed.

**NSE session (IST):**

  * Pre-open: 09:00-09:08 order entry, matching up to 09:15.
  * Normal market: 09:15-15:30.
  * Closing session: 15:40-16:00 (not used).
  * Angel auto-squares-off open MIS positions in the afternoon (about 15:15-15:20) and charges a fee. Our engine closes everything at **15:05**.
  * Special sessions (Muhurat trading on Diwali, rare Saturday sessions) come from the holiday/special-session file.



**Taxes (for the CA export):** intraday profit counts as speculative business income (taxed at slab rate, ITR-3). Delivery gains are short-term capital gains at 20% under 12 months, and long-term at 12.5% above ₹1.25 lakh a year.

## A4. Architecture and decisions table
    
    
                Angel One SmartAPI (REST + WebSocket V2 + order-update WS)
                     |  login(TOTP) / candles / quotes / orders            NSE archives (bhavcopy, index list, holidays)
                     v                                                          |
      broker/angel.py  <--- same Broker protocol --->  broker/paper.py          v
            |                                               |            data/history.py
            v                                               v                   |
      data/stream.py -> ticks -> 1m bars (data/bars.py) -> lake (Parquet)  <----+
            |                                    |
            v                                    v
      engine/runner.py (APScheduler, IST clock) -> strategies/* (pure) -> core/risk.py (pure)
            |                                          -> core/orders.py (state machine) -> Broker
            v
      engine/state.py (SQLite)  ->  web/ (portal + JSON API)  ->  notify/telegram.py
      lab/ (backtest, evaluate, ledger): runs the SAME strategies/costs/risk on stored bars
    

Topic| Decision  
---|---  
Repository| New **private** GitHub repo `dhruvparekhdp/nse-engine`. `main` deploys to the server. Cursor works on `feat/<phase>-<topic>` branches and opens PRs.  
Language| Python 3.12. One process, asyncio. CPU-heavy work (backtests) runs offline or in `asyncio.to_thread`.  
Libraries| `smartapi-python` (Angel's official SDK), `pyotp`, `aiohttp`, `apscheduler<4`, `pydantic-settings`, `pandas`, `numpy`, `pyarrow`, `structlog`, `httpx`, `bcrypt`, `yfinance` (research only). Dev: `pytest`, `pytest-asyncio`, `ruff`. Exact versions are pinned in `requirements.txt` at P0 and recorded in DECISIONS.md.  
Storage| **SQLite in WAL mode** , `data/engine.db`, for state (orders, trades, signals, settings, audit). **Parquet lake** `data/lake/` for bars. No database server; nothing shared with the crypto engine.  
Time| Store **UTC epoch milliseconds** (int). Display and schedule in IST (`zoneinfo.ZoneInfo("Asia/Kolkata")`). Never naive datetimes. A bar's timestamp is its **open** time.  
Money| Rupees as float, rounded to 2 decimals only for display. Prices are rounded to the instrument's tick size (0.05 for most NSE stocks; read `tick_size` from the scrip master) before any order.  
Process| systemd service `nse-engine`, user `ubuntu`, `MemoryMax=600M`, `Restart=on-failure`, `RestartSec=10`.  
Web access| The portal binds to `127.0.0.1:8090`. The owner reaches it through **Tailscale** (`tailscale serve`, installed on the EC2 in P0 with the owner's OK). No public port is opened.  
Deploy| GitHub Actions: CI (ruff + pytest), then SSH deploy (`git pull`, `pip install -r requirements.txt`, `systemctl restart nse-engine`). **Blocked Mon-Fri 09:00-15:45 IST** , unless a manual dispatch passes `force=true`.  
Mode| `mode` = `paper` (default) or `live`. `live_orders` = false by default. Real orders need **both** `mode=live` and `live_orders=true`, set by the owner in `.env`. Tests can never enable them.  
  
## A5. Repository layout (every file)
    
    
    nse-engine/
      AGENTS.md                      rules for Cursor/agents (A17) - read first, every chat
      README.md                      what it is, how to run locally, how to test
      docs/PLAN.md                   this document as Markdown (source of truth)
      docs/DECISIONS.md              dated log of every decision/answer from the owner
      docs/SERVER_SETUP.md           one-time server steps (A14)
      docs/RUNBOOK.md                what to do when: login fails, WS drops, kill switch, broker outage
      requirements.txt, requirements-dev.txt, pyproject.toml (ruff + pytest config)
      .env.example                   names only, no values
      config/settings.py             pydantic-settings (A6)
      config/costs_angel.json        cost rates + source URL + date (A2.1)
      config/holidays_2026.json      NSE trading holidays + special sessions (yearly file)
      config/universe_overrides.json symbols to exclude/include manually (starts empty)
      broker/base.py                 Broker protocol + dataclasses (Order, Fill, Position, Funds, Quote)
      broker/angel.py                SmartAPI implementation (A8)
      broker/paper.py                PaperBroker (A9.5)
      broker/errors.py               typed errors: AuthError, RateLimited, Rejected, Unavailable
      data/instruments.py            Nifty 100 list + Angel token map
      data/calendar.py               trading days, sessions, special sessions
      data/stream.py                 websocket client (thread) -> asyncio queue of ticks
      data/bars.py                   ticks -> 1m bars (+5m/15m/daily resample), spread snapshots
      data/lake.py                   Parquet read/append/dedupe
      data/history.py                Angel candle backfill, NSE bhavcopy, yfinance (research)
      data/health.py                 data-quality checks + report
      core/clock.py                  IST helpers + session state machine
      core/indicators.py             VWAP, ATR, RSI, EMA, opening range, rolling volume by slot
      core/costs.py                  cost model (pure)
      core/risk.py                   sizing + limits (pure)
      core/orders.py                 order manager (state machine, bracket emulation, watchdog, reconcile)
      core/types.py                  Signal, Bar, TradePlan, Decision dataclasses
      strategies/base.py             Strategy protocol, mirror(), random_baseline()
      strategies/orb.py, vwap_revert.py, gap.py, intraday_momentum.py, pdh_rs.py, swing_breakout.py
      lab/backtest.py                event-driven backtester (same objects as live)
      lab/evaluate.py                splits, gate, baselines, cost stress, report
      lab/ledger.py                  counts every trial (SQLite table lab_trials)
      engine/state.py                SQLite schema, migrations, repository functions
      engine/runner.py               scheduler + wiring + jobs (A12)
      engine/parity.py               daily paper/live vs replay comparison
      web/app.py                     aiohttp app, auth, JSON API (A13)
      web/static/                    index.html, app.js, style.css (vanilla JS + Chart.js 4 from cdnjs)
      notify/telegram.py             sender + command handler
      scripts/backfill.py, research.py, report.py, parity.py, login_check.py, export_tax.py
      deploy/nse-engine.service      systemd unit
      .github/workflows/ci.yml, deploy.yml
      tests/                         mirrors the package layout; fixtures/ holds recorded API JSON
      data/                          (git-ignored) engine.db, lake/, logs/, backups/
    

## A6. Configuration (every setting)

All settings live in `config/settings.py` (pydantic-settings, reading `.env`). A few can be changed at runtime from the portal: those marked runtime are stored in the SQLite `settings` table, which overrides `.env`.

Name| Type| Default| Meaning  
---|---|---|---  
angel_api_key| SecretStr| (none)| SmartAPI app key (.env only)  
angel_client_code| SecretStr| (none)| Angel login ID  
angel_pin| SecretStr| (none)| 4-digit MPIN  
angel_totp_secret| SecretStr| (none)| base32 secret from "Enable TOTP"  
telegram_bot_token / telegram_chat_id| SecretStr / str| (none)| alerts; no-op when empty  
portal_admin_hash| str| (none)| bcrypt hash of the admin password  
session_secret| SecretStr| (none)| HMAC key for session cookies  
mode| "paper"|"live"| paper| which broker the engine trades through  
live_orders| bool| false| second switch, required for any real order  
kill_switch| bool runtime| false| no new orders; open positions keep their stops  
books_enabled| list runtime| ["A","B"]| which books may open trades  
strategies_enabled| list runtime| [] until P3 passes| strategy ids allowed to open trades (paper or live)  
capital_inr| float| 50000| paper capital; live reads funds from Angel  
risk_per_trade_pct| float runtime| 1.0| % of capital lost if the stop is hit  
first_live_risk_pct| float| 0.5| risk % during the first 2 live weeks  
min_position_inr| float| 100000| Book A: skip trades smaller than this (A2.1)  
max_position_pct_capital| float| 300| Book A: position value at most 3x capital  
max_mis_exposure_x| float| 3.0| sum of open MIS position values at most 3x capital (Angel allows up to ~5x)  
max_open_intraday / max_open_swing| int| 3 / 5| open position limits  
daily_loss_limit_pct| float| 2.0| stop new intraday entries for the day after this realised + open loss  
floor_pct| float| 80| below this % of start capital: kill switch on + alert  
no_entry_after| "HH:MM" IST| 14:45| Book A: last entry time  
square_off_at| "HH:MM" IST| 15:05| Book A: close every MIS position  
max_spread_pct| float| 0.10| skip the entry if (ask-bid)/mid is larger  
circuit_buffer_pct| float| 2.0| skip if price is within this % of the upper/lower circuit  
entry_limit_offset_pct| float| 0.05| marketable limit: best ask x (1+offset) for buys  
entry_timeout_s| int| 20| cancel an unfilled entry after this  
stop_limit_buffer_pct| float| 0.5| stop-limit price beyond the trigger  
stop_watchdog_s| int| 10| if price traded through the trigger and the stop is still open, exit with a protected limit  
orders_per_second| int| 5| throttle (SEBI cap is 10)  
history_min_interval_s| float| 0.4| gap between candle-history calls  
slippage_pct_mis / slippage_pct_cnc| float| 0.03 / 0.05| paper/backtest slippage per side  
ws_mode| int| 3| WebSocket V2 mode: 1 LTP, 2 Quote, 3 SnapQuote (needs best bid/ask)  
tick_stale_alert_s| int| 30| alert when no tick for this long in market hours  
expected_static_ip| str| (none)| the Elastic IP registered on the SmartAPI app; live orders are blocked if the public IP differs (A8)  
web_host / web_port| str / int| 127.0.0.1 / 8090| portal bind  
data_dir| path| ./data| db, lake, logs, backups  
  
## A7. Data model

### A7.1 SQLite tables (engine/state.py; migrations are numbered SQL files; table `schema_version`)

Table| Columns (type)| Notes  
---|---|---  
instruments| symbol TEXT PK (e.g. "SBIN"), token TEXT, trading_symbol TEXT ("SBIN-EQ"), name, isin, tick_size REAL, lot_size INT, in_universe INT, updated_ms INT| refreshed daily from the scrip master  
sessions| trade_date TEXT PK (YYYY-MM-DD IST), login_ok INT, login_ms INT, feed_ok INT, error TEXT| one row per day  
signals| id INT PK, ts_ms, trade_date, symbol, book ("A"/"B"), strategy, side (+1/-1), role ("pick"/"mirror"/"random"), price REAL, stop REAL, target REAL, features_json TEXT, decision ("taken"/"skipped"/"shadow"), skip_reason TEXT| mirror and random rows are always "shadow" (never traded)  
orders| id INT PK, client_tag TEXT UNIQUE, broker_order_id TEXT, trade_id INT, symbol, side, qty INT, order_type ("LIMIT"/"STOPLOSS_LIMIT"), product ("INTRADAY"/"DELIVERY"), purpose ("entry"/"stop"/"target"/"exit"), price REAL, trigger REAL, status, filled_qty INT, avg_price REAL, placed_ms, updated_ms, mode, error TEXT| status values in A9.4  
trades| id INT PK, signal_id, symbol, book, strategy, side, qty, entry_ms, entry_price, stop_init, stop_now, target, exit_ms, exit_price, exit_reason ("stop"/"target"/"square_off"/"time"/"manual"/"kill"), gross_inr, costs_inr, net_inr, r_mult, mode, status ("open"/"closed")| r_mult uses stop_init (lesson from crypto: never the trailed stop)  
daily_pnl| trade_date, mode, book, start_inr, realized_inr, costs_inr, end_inr, trades INT; PK(trade_date, mode, book)| written at 15:45  
events| id INT PK, ts_ms, kind TEXT, json TEXT| audit log: login, order sent, fill, rejection, kill, settings change  
settings| key TEXT PK, value_json TEXT, updated_ms, updated_by| runtime overrides  
lab_trials| id INT PK, ts_ms, strategy, params_json, data_from, data_to, period, n INT, avg_r REAL, win_pct REAL, passed INT, report_path TEXT| every research run  
parity| trade_date, mode, book, signals_live INT, signals_replay INT, matched INT, avg_fill_diff_pct REAL, faults_json TEXT| daily  
  
### A7.2 Parquet lake (data/lake/)

Dataset| Path| Columns  
---|---|---  
1-minute bars| `bars_1m/SYMBOL/YYYY-MM.parquet`| ts_ms int64 (bar open, UTC), open, high, low, close float64, volume int64, n_ticks int32, source str ("ws"/"hist")  
Spread snapshots| `spread_1m/SYMBOL/YYYY-MM.parquet`| ts_ms, bid, ask, bid_qty, ask_qty (last snapshot each minute)  
Daily bars| `bars_1d/SYMBOL.parquet`| date int (YYYYMMDD), open, high, low, close, volume, delivery_qty, source ("bhav"/"angel"/"yf"), adj_close (yf only)  
Index bars| `bars_1m/NIFTY50/...`, `bars_1m/INDIAVIX/...`| same as stocks (volume 0)  
  
Rules: append-only; dedupe on ts_ms keeping `ws` over `hist`; raw ticks are **not** stored (size). One writer: the runner process.

## A8. Angel One SmartAPI integration (broker/angel.py)

Use the official Python SDK (`from SmartApi import SmartConnect`, `from SmartApi.smartWebSocketV2 import SmartWebSocketV2`). Wrap every SDK call in `asyncio.to_thread` because the SDK is blocking. Cursor must read the current SmartAPI docs for exact field names. The names below are from the documented SDK and must be confirmed against recorded responses in `tests/fixtures/angel/`.

Need| SDK call| Notes  
---|---|---  
Login| `SmartConnect(api_key).generateSession(client_code, mpin, pyotp.TOTP(secret).now())`| returns jwtToken, refreshToken, feedToken. Keep them in memory only. Retry once after 30 s on failure, then alert.  
Profile / funds| `getProfile(refreshToken)`, `rmsLimit()`| funds: `availablecash`, `net`, utilised margins  
Quote| `ltpData(exchange, tradingsymbol, token)`; full quote via the market-data quote endpoint (mode FULL) for circuit limits| circuit limits: upper/lower circuit fields in the FULL quote  
History| `getCandleData({exchange, symboltoken, interval, fromdate "YYYY-MM-DD HH:MM", todate})`| intervals ONE_MINUTE, FIVE_MINUTE, FIFTEEN_MINUTE, ONE_HOUR, ONE_DAY. 1-minute: 30 days per call. Throttle (A6). AB1021 means wait 2 s and retry with backoff (max 5).  
Live data| `SmartWebSocketV2(jwt, api_key, client_code, feed_token)`; `subscribe(correlation_id, mode, [{"exchangeType": 1, "tokens": [...]}])`| exchangeType 1 = NSE cash. Mode 3 = SnapQuote (LTP, volume, OHLC, best 5 bid/ask). Max 1000 tokens per connection. Runs in its own thread and pushes ticks into an asyncio queue via `loop.call_soon_threadsafe`. Reconnect with backoff 1, 2, 5, 10, 30 s.  
Order updates| the SDK's order-update websocket (or poll `orderBook()` every 2 s as fallback)| both paths feed `core/orders.py`  
Place order| `placeOrder({variety, tradingsymbol, symboltoken, transactiontype, exchange:"NSE", ordertype, producttype, duration:"DAY", price, triggerprice, quantity, ordertag})`| variety NORMAL (entries/targets) or STOPLOSS (stops); ordertype LIMIT or STOPLOSS_LIMIT; producttype INTRADAY (Book A) or DELIVERY (Book B). `ordertag` = our client tag (check its max length; default format in A9.4 is 16 chars).  
Modify / cancel| `modifyOrder({...orderid...})`, `cancelOrder(order_id, variety)`| counted in the throttle  
Book / positions / holdings| `orderBook()`, `tradeBook()`, `position()`, `holding()`| used by reconciliation every 30 s and at start-up  
Instrument master| HTTP GET `https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json`| about 30-40 MB JSON. Filter `exch_seg=="NSE"` and `symbol` ending in "-EQ". Fields: token, symbol, name, tick_size (paise), lotsize. Nifty 50 and India VIX index tokens: look up by name ("Nifty 50", "India VIX"); expected 99926000 and 99926017 (verify).  
  
**Error handling.** Map responses to `broker/errors.py`:

  * token or session invalid becomes `AuthError`, and the engine re-logs in once;
  * AB1021 or "too many requests" becomes `RateLimited`, with backoff;
  * a rejection with a message becomes `Rejected`, logged and alerted, with no retry for orders;
  * network errors or 5xx become `Unavailable`, retried for reads only.



Every unknown error code is logged with the full message (never the tokens) and added to `docs/RUNBOOK.md`.

**Static-IP self-check.** Before the first live order of the day, the engine asks `https://api.ipify.org` for its public IP. If it differs from `settings.expected_static_ip`, it turns on the kill switch and alerts.

## A9. Core modules

### A9.1 core/clock.py

  * `now_ms()`, `to_ist(ms)`, `ist_today()`.
  * `session_state(ms)` returns one of PRE_OPEN, OPEN, NO_NEW_ENTRIES (after 14:45), SQUARE_OFF (15:05-15:30), CLOSED, HOLIDAY.
  * All times come from settings and the calendar (special sessions override).
  * Tests freeze time with an injectable clock (no global patching).



### A9.2 core/costs.py
    
    
    @dataclass(frozen=True)
    class CostBreakdown: brokerage, stt, exchange, sebi, stamp, gst, dp, total   # rupees
    
    def order_brokerage(value: float, rates) -> float           # min(flat, pct*value)
    def round_trip(buy_value: float, sell_value: float, product: Literal["MIS","CNC"], rates) -> CostBreakdown
    def cost_in_r(position_value: float, stop_pct: float, product, rates, slippage_pct) -> float
    

Test vectors: the four intraday rows and the delivery example in A2.1 (to the paisa, using the defaults), plus the owner's calculator screenshots once provided.

### A9.3 core/risk.py (pure functions)
    
    
    def size(entry, stop, capital, risk_pct, tick, book, limits) -> SizeResult(qty, value, reason)
       qty = floor(capital*risk_pct/100 / abs(entry-stop)); value = qty*entry
       Book A: if value < min_position_inr -> qty=0 reason "below_min_position"
               value capped at capital*max_position_pct_capital/100
       Book B: value capped at capital/max_open_swing (equal slots)
    def can_open(state, plan, limits, now) -> (bool, reason)
       checks in this order: kill_switch, floor, daily_loss_limit, session time, max_open, MIS exposure,
       same symbol already open (one position per symbol), spread guard, circuit buffer, results-day block
    

Every "no" returns a short machine reason (e.g. `spread_wide`), stored on the signal row as `skip_reason`.

### A9.4 core/orders.py: order manager

**Order states:** NEW, SUBMITTED, OPEN, PARTIAL, FILLED, CANCELLED, REJECTED, EXPIRED. **Client tag:** `ne{yyMMdd}{book}{strategy 2 chars}{seq 4 digits}`, for example `ne261023AOR0007`. It is unique and makes retries safe: before resending, the manager looks up the tag in the broker's order book.

**Bracket emulation** (an entry with its exit orders):

  1. Send the entry: a LIMIT at best ask x (1 + entry_limit_offset_pct) for buys (mirror for sells), rounded to the tick.
  2. If it isn't filled within entry_timeout_s, cancel it. A partial fill is kept and the rest cancelled.
  3. On fill, place the **stop** at once: STOPLOSS_LIMIT with the trigger at the stop and the limit at the trigger ± stop_limit_buffer_pct. Then place the **target** as a LIMIT (if the strategy has a target).
  4. One-cancels-other: when the target fills, cancel the stop; when the stop fills, cancel the target.
  5. **Watchdog:** if the last traded price has crossed the trigger for longer than stop_watchdog_s and the stop is still open, cancel it and send a LIMIT exit 0.5% through the market (repeat every 5 s, max 6).
  6. Square-off at 15:05 for Book A: cancel the stop and target, and send a protected LIMIT exit.
  7. **Reconcile** every 30 s and at start-up: compare our open orders and positions with the broker's. Any difference raises an alert, and the broker's view wins for positions. Never open a new entry while a reconcile difference is unresolved for that symbol.



### A9.5 broker/paper.py: PaperBroker

  * It implements the Broker protocol and is fed live ticks (or bars in backtests).
  * **Limit buy** fills at the first tick with ask ≤ limit, at min(limit, ask) + slippage. With no ask in the tick, it fills when LTP ≤ limit.
  * **Stop-limit sell** triggers at the first tick with LTP ≤ trigger and fills at min(LTP, trigger) − slippage − 0.05% (stops fill worse). If the price gaps through the limit, it stays open (the watchdog handles it, as live).
  * Fills are full fills (Nifty 100 sizes). Costs come from `core/costs.py`. It keeps cash, MIS margin used (20% of value) and positions.
  * Same tag rules and the same rejections as live: insufficient funds, outside session, price outside the circuit.



## A10. Strategies (pre-registered; parameters fixed before any test)

Interface (strategies/base.py):
    
    
    class Strategy(Protocol):
        id: str            # "S1_orb" ...
        book: str          # "A" or "B"
        timeframe: str     # "5m" or "1d"
        def on_bar(self, symbol: str, bars: BarView, ctx: Context) -> list[Signal]: ...
    Signal(ts_ms, symbol, side, entry_ref, stop, target|None, time_exit_ms|None, features: dict)
    mirror(sig)          -> same entry time/price, opposite side, stop at same % distance, same target R
    random_baseline(sig) -> same symbol/day, random entry minute within the strategy's allowed window
                            (seeded by hash(signal id) for determinism), same side and stop %, same exit rules
    

`BarView` only exposes bars that have **closed** before the decision time. A test feeds a future bar and expects an exception.

Id| Book| Rule (long; short is the symmetric rule; long-only where noted)| Exit  
---|---|---|---  
S1_orb| A| Opening range (OR) = high/low of 09:15-09:30. Long on the first 5m bar that **closes** above OR high between 09:30 and 11:30, with that bar's volume > 1.5x the 20-day average volume of the same 5m slot. Skip if OR width < 0.4% or > 2.5% of price, or |overnight gap| > 3%.| stop OR low; target 2R; else exit 15:05  
S2_vwap| A| After 10:30: price closes (5m) more than 2 standard deviations below session VWAP (std of close−VWAP since open) and 5m RSI(14) < 25.| target VWAP; stop 1 std below entry; exit 15:05  
S3_gapfade| A| Gap ≥ +1.5% vs previous close and the first 15m bar (09:15-09:30) closes below its open: **short** toward the previous close (gap down mirrors: long). Variant S3b "gap-and-go": the first 15m bar closes in the gap's direction, trade with the gap. Both tested, counted as 2 trials.| stop beyond the first 15m extreme; target previous close (S3) / 2R (S3b); exit 15:05  
S4_momo| A| At 14:00: the stock's 09:15-10:15 return is in the top decile of the Nifty 100 and price is above VWAP: long (bottom decile and below VWAP: short).| stop 1x ATR(14, 5m); exit 15:05  
S5_pdh_rs| A| Price breaks the previous day's high between 09:45 and 13:30, and the stock's return since the open minus Nifty 50's is in the top 10 of the universe at that moment.| stop = session VWAP at entry (skip if >1.5% away); target 2R; exit 15:05  
S6_swing| B| **Long-only.** Daily close above the 20-day highest high (Donchian 20) with the 50-day SMA rising; variant S6b: close above the Keltner channel (EMA20 + 2xATR20). Orders placed for the next day 09:15 as LIMIT at previous close +0.5%.| stop 2.5x ATR(14) below entry, trailed to the highest close − 2.5x ATR; exit after 20 sessions  
  
Everyone's context features (stored with each signal, for later ML): gap %, OR width %, distance to VWAP, ATR %, India VIX, Nifty return since open, day of week, minutes since open, whether results are due within 3 days, spread %, 20-day average turnover.

## A11. Backtester and research lab

  * **lab/backtest.py:** replays 1-minute bars per trading day across the universe. At each bar close it calls every enabled strategy, then `risk.can_open` and `risk.size`, then executes through **PaperBroker** using bar OHLC with a fixed fill order (open, then the worse of high/low first for the position, then close). It produces trades with the same columns as the live `trades` table. It is **deterministic** : same inputs, same outputs.
  * **lab/evaluate.py:**
    * Splits the available history into two halves by date.
    * For each strategy it reports n, win %, average R after costs, total R, maximum drawdown (R and ₹), and results by year, by India VIX tercile and by results-season. It also reports the **mirror** and **random** baselines and a **cost stress** run (costs x1.5).
    * **Gate** (all must hold): 
      * average R ≥ +0.10 after costs in both halves;
      * n ≥ 200 per half (Book B: ≥ 100);
      * it beats the mirror and the random baseline in both halves;
      * average R > 0 under cost stress.
  * **lab/ledger.py:** every run writes a `lab_trials` row, so the report shows "trials so far: N". Parameter changes after seeing a result are a new trial with a new id and are flagged as post-hoc.
  * **scripts/research.py:** `python -m scripts.research --strategy S1_orb --from 2025-11-01 --to 2026-10-31` writes `data/reports/S1_orb_<date>.json` plus a chart JSON. The portal Lab page shows it.



## A12. Engine runtime (engine/runner.py)

### A12.1 Daily schedule (IST, trading days only; on holidays only the night jobs run)

Time| Job  
---|---  
08:30| refresh the instrument master and universe (weekly: NSE Nifty 100 list), load today's calendar; check that results-day data is current  
08:45| login (TOTP), then funds check, then reconcile with the broker. On failure retry at 08:50 and 08:55, then alert and fall back to the Telegram TOTP prompt  
09:00| start the websocket and subscribe the universe + NIFTY50 + INDIAVIX; Book B: send today's swing entries (LIMIT) prepared last evening  
09:15-15:30| each tick goes to the bar builder; each 1-minute close triggers the strategies, then risk, then orders; the order manager loop runs every 1 s; reconcile every 30 s; health every 60 s  
14:45| Book A: no new entries  
15:05| Book A: square off every MIS position (A9.4)  
15:35| stop the websocket; flush bars; verify zero open MIS positions with the broker (alert if not)  
15:45| end-of-day: daily_pnl rows, Telegram summary, the parity job (A12.2), Book B signal scan on the daily close  
18:00| history backfill for any missing minutes (from Angel candles), NSE bhavcopy download, data-health report  
18:30| backups (A14)  
  
### A12.2 Parity check (engine/parity.py)

Each evening it replays the day's recorded bars through the backtester and compares the result with the trades the engine made (paper or live):

  * the same signals (symbol, strategy, side, minute);
  * fill price differences (average and worst, in %);
  * missing or extra trades, each with a reason.



A fault is an unexplained mismatch. Two fault days in a row turn on the kill switch while live.

### A12.3 Safety summary

The following all stop new entries and leave open positions with their exchange stops:

  * the kill switch (portal, Telegram `/kill`, floor breach, static-IP mismatch, parity faults);
  * the daily loss limit (Book A only, for the rest of the day);
  * a stale feed (no tick for 30 s in market hours): new entries pause, alert after 60 s;
  * an unresolved reconcile difference (for that symbol).



## A13. Portal, API and Telegram

### A13.1 Pages (phone first; plain English; Chart.js 4 from cdnjs with a pinned version)

  * **Today:**
    * mode banner ("PAPER" / "LIVE: real money");
    * capital, today's P&L; after costs, costs paid;
    * open positions with stop and target;
    * today's orders with status;
    * an equity curve for the day.
  * **Signals:** every signal with its mirror and random rows, filters (book, strategy, taken/skipped, won/lost), skip reasons in words.
  * **Books:** A and B side by side: equity curve, R per trade histogram, win rate, average R, costs as % of gross, by strategy, by month; drill down to each trade.
  * **Lab:** each strategy's gate table (A11) with a pass/fail chip; trials count.
  * **Data:** feed status, last tick age, missing minutes per symbol today, history depth per symbol, backfill status.
  * **Settings** (admin): kill switch, books and strategies enabled, risk %. Every change is written to `events`.



### A13.2 JSON API (aiohttp; admin cookie required for POST)
    
    
    GET  /api/health          {ok, mode, live_orders, kill_switch, session_state, login_ok, ws_connected, last_tick_age_s, open_positions}
    GET  /api/today           {capital, pnl_inr, costs_inr, positions[], orders[], equity_curve[]}
    GET  /api/signals?date=&book=&strategy=&decision=
    GET  /api/trades?from=&to=&book=&strategy=&mode=
    GET  /api/books           per book/strategy aggregates
    GET  /api/lab             latest report per strategy + trials count
    GET  /api/data-health     per-symbol coverage
    POST /api/login           {password} -> sets HMAC-signed cookie (12 h)
    POST /api/settings        {key, value}   (whitelisted keys only)
    POST /api/kill            {on: true|false}
    

### A13.3 Telegram (notify/telegram.py)

  * **Messages:**
    * 08:45 login result;
    * each entry, exit and rejection (symbol, side, qty, price, ₹ risk);
    * 15:45 daily summary;
    * errors and safety triggers immediately.
Quiet outside 08:30-16:00 except errors.
  * **Commands** (only from `telegram_chat_id`): `/status`, `/positions`, `/kill`, `/resume`, `/totp 123456` (fallback login).
  * No message ever contains keys, tokens or the full account number.



## A14. Deployment, server, backups, security

### A14.1 One-time server setup (docs/SERVER_SETUP.md; the owner runs or approves each step)

  1. AWS console, region ap-southeast-2: give the EC2 an **Elastic IP** (or confirm the current 52.62.37.4 is one). Record it as `expected_static_ip`.
  2. Verify Angel accepts an Australian static IP: place one tiny paper-safe test in P5 (a far-from-market LIMIT buy of 1 share, then cancel it) only with the owner's yes. If it's rejected for location, move to a small ap-south-1 (Mumbai) instance.
  3. Install Tailscale on the EC2 (owner logs in). The portal is reached at the EC2's tailnet name with `tailscale serve 8090`.
  4. Clone the repo to `/home/ubuntu/nse-engine`, create `.venv`, copy `.env` (owner types the secrets on the server, never in git or chat), `chmod 600 .env`.
  5. Install the systemd unit (below), `systemctl enable --now nse-engine`.
  6. GitHub repo secrets for deploy: `EC2_HOST`, `EC2_USER`, `EC2_SSH_KEY` (a deploy key used only for this repo).


    
    
    # deploy/nse-engine.service
    [Unit]
    Description=NSE equity engine
    After=network-online.target
    [Service]
    User=ubuntu
    WorkingDirectory=/home/ubuntu/nse-engine
    ExecStart=/home/ubuntu/nse-engine/.venv/bin/python -m engine.runner
    Restart=on-failure
    RestartSec=10
    MemoryMax=600M
    Environment=PYTHONUNBUFFERED=1
    [Install]
    WantedBy=multi-user.target
    
    
    
    # .github/workflows/deploy.yml (essentials)
    on: { push: { branches: [main] }, workflow_dispatch: { inputs: { force: { default: "false" } } } }
    jobs:
      test:   ruff check . && pytest -q
      deploy: needs: test
        - name: block market hours
          run: |
            d=$(TZ=Asia/Kolkata date +%u); t=$(TZ=Asia/Kolkata date +%H%M)
            if [ "${{ inputs.force }}" != "true" ] && [ $d -le 5 ] && [ $t -ge 0900 ] && [ $t -le 1545 ]; then
              echo "Market hours (IST) - deploy blocked. Re-run after 15:45 or dispatch with force=true."; exit 1; fi
        - ssh: cd ~/nse-engine && git pull --ff-only && .venv/bin/pip install -q -r requirements.txt
               && sudo systemctl restart nse-engine && sleep 8 && curl -fs 127.0.0.1:8090/api/health
    

### A14.2 Backups

  * 18:30 IST daily: an SQLite online backup (`sqlite3 engine.db ".backup ..."`, gzip) to `~/backups/nse/engine-YYYYMMDD.db.gz`, kept 30 days.
  * The day's new Parquet files are tarred to `~/backups/nse/lake-YYYYMMDD.tar`, kept 14 days.
  * The recorded bars cannot be re-downloaded, so on the 1st of each month the owner copies the lake to the Mac. A script prints the command.



### A14.3 Security

  * Secrets only in the server's `.env` (chmod 600), loaded as `SecretStr`. A `structlog` processor masks any key named token, secret, pin, password or jwt.
  * The portal is reachable only over Tailscale. Admin uses a bcrypt password and an HMAC cookie. Never log request bodies of `/api/login`.
  * Run `gitleaks` (or ruff + a regex check) in CI to block committed secrets.
  * The repo is private. The crypto repo is public, so never copy this project's `.env` or data there.



## A15. Testing standards

  * Every change has a test that **fails before and passes after**. CI must be green before review.
  * **No network in tests.**
    * Angel calls go to a fake broker, or to an aiohttp fake server replaying `tests/fixtures/angel/*.json` (recorded once from real responses with secrets removed).
    * NSE files go to fixtures.
  * Required tests: 
    * **clock:** session states on a normal day, a holiday and Muhurat.
    * **costs:** the A2.1 vectors.
    * **risk:** each limit returns its reason; sizing rounding; the min-position rule.
    * **orders:** partial fill, timeout cancel, OCO, the watchdog, retry by tag (no duplicate), reconcile difference.
    * **paper broker:** limit/stop fills and the gap-through case.
    * **bars:** late tick, missing minute, out-of-order tick.
    * **strategies:** each rule on a hand-built day (it fires and doesn't fire); no lookahead (a future bar raises).
    * **backtest:** deterministic; the costed vs cost-free difference equals the sum of costs.
    * **evaluate:** the gate fails on shuffled outcomes.
    * **web:** auth required for POST; health shape.
    * **safety:** `live_orders` can't be true in tests (conftest asserts).



## A16. Phases and tickets

Each phase is one branch and one PR. A ticket is done only when its tests pass and its acceptance line is met. At the end of each phase Cursor writes a short `docs/phase-reports/Pn.md`: what was built, the test count, the acceptance numbers, and open questions for the owner.

### P0: Foundation branch feat/p0-foundation

Ticket| Work| Done when  
---|---|---  
P0-1| Create the layout (A5), `pyproject.toml` (ruff line length 120; pytest asyncio_mode=auto), pinned requirements, `.gitignore` (data/, .env, *.db*, .venv), `.env.example`, AGENTS.md (A17 verbatim), docs/PLAN.md (this document), docs/DECISIONS.md (first entry: the owner's decisions in A1)| `ruff check .` and `pytest -q` both pass on an empty test  
P0-2| `config/settings.py` with every setting in A6; runtime overrides from the SQLite `settings` table via `get_setting(key)`| tests: defaults; .env override; runtime override; `live_orders` forced false under pytest  
P0-3| `core/clock.py` \+ `data/calendar.py` \+ `config/holidays_2026.json` (Cursor fills it from NSE's 2026 holiday list and the owner verifies)| tests: session states for 3 day types; DST-free IST maths; weekend  
P0-4| `engine/state.py`: SQLite WAL, migrations 001_init.sql (all A7.1 tables), repository functions| tests: migrate an empty db; insert/read each table; second migrate is a no-op  
P0-5| `web/app.py`: health endpoint, login/cookie, static shell page with the PAPER banner| tests: health shape; POST without cookie gives 401  
P0-6| `notify/telegram.py`: send (no-op when unconfigured), command router with a chat-id check| tests with a fake Telegram API  
P0-7| `engine/runner.py`: APScheduler with the A12.1 jobs as stubs that log; graceful shutdown (SIGTERM flushes and closes)| the service starts with no Angel keys and `/api/health` says "not configured"  
P0-8| CI and deploy workflows (A14.1), systemd unit, docs/SERVER_SETUP.md, docs/RUNBOOK.md skeleton| CI green on the PR; a deploy dry run is blocked in market hours (unit-test the time check as a small script)  
  
### P1: Data branch feat/p1-data

Ticket| Work| Done when  
---|---|---  
P1-1| `data/instruments.py`: download the scrip master (streamed, about 35 MB), filter NSE -EQ, join the Nifty 100 list (`https://archives.nseindia.com/content/indices/ind_nifty100list.csv`, browser-like User-Agent; verify URL), write `instruments`; resolve the NIFTY50 / INDIAVIX tokens| fixture test: 100 symbols mapped, tick sizes converted from paise; a missing symbol is listed in the report, not silently dropped  
P1-2| `broker/angel.py` login + profile + funds + quote (read-only parts) with error mapping and throttle; `scripts/login_check.py` (the owner runs it on the server)| fake-server tests for success, a bad TOTP and AB1021; the owner's real run prints 4 OK lines  
P1-3| `data/history.py` Angel backfill: per symbol, walk back in 30-day windows (1m) until empty or error, throttled; resumable (state in a json per symbol); dedupe into the lake; also ONE_DAY| fixture tests: window maths, resume, dedupe; the real run report shows **history depth per symbol** (decision point A2.4)  
P1-4| NSE bhavcopy downloader (new UDiFF zip format and the old format; verify URLs at build time) into `bars_1d`; yfinance adjusted daily for research (source "yf")| fixture tests for both formats; SBIN daily bars 2015-2026 with no gaps on trading days  
P1-5| `data/stream.py`: WebSocket V2 in a thread, SnapQuote mode, reconnect/backoff, heartbeat, subscribe the universe + indices| fake-WS test: reconnect after a drop resubscribes; ticks cross threads safely  
P1-6| `data/bars.py`: ticks become 1m bars keyed by exchange time (IST minute), late ticks (≤ 5 s) go into the previous bar, out-of-order handled, flushed every minute with source "ws"; spread snapshot per minute; 5m/15m/daily resample helpers| tests: late/out-of-order/missing minute; a resample matches hand maths  
P1-7| `data/health.py` \+ Data page: missing minutes per symbol per day, last tick age, history depth| one full live session recorded for 100 symbols with < 0.5% missing minutes; recorded bars match Angel 1m candles (backfilled that evening) within 1 tick on 3 sampled symbols  
  
### P2: Trading core branch feat/p2-core

Ticket| Work| Done when  
---|---|---  
P2-1| `core/costs.py` \+ `config/costs_angel.json` (rates, source URL, date)| A2.1 vectors to the paisa; then updated to the owner's calculator screenshots  
P2-2| `core/indicators.py` (VWAP from session start, ATR Wilder 14, RSI Wilder 14, EMA, SMA, OR high/low, slot-volume average over 20 days, Donchian, Keltner)| each against a hand-computed small series  
P2-3| `core/risk.py` (A9.3)| a test per limit and reason  
P2-4| `broker/paper.py` (A9.5)| fill tests incl. the gap-through stop  
P2-5| `core/orders.py` (A9.4) working against the Broker protocol| the tests listed in A15 for orders  
P2-6| `strategies/base.py` \+ BarView (no lookahead) + mirror/random helpers| a future bar raises; random baseline deterministic for a seed  
P2-7| `lab/backtest.py`, `lab/evaluate.py`, `lab/ledger.py`, `scripts/research.py`| deterministic; the cost difference equals the sum of costs; the gate fails on shuffled outcomes; the trials count increments  
  
### P3: Research branch feat/p3-research

Ticket| Work| Done when  
---|---|---  
P3-1 to P3-6| implement S1-S6 exactly as A10 (one ticket each), with tests on hand-built days| each strategy fires and doesn't fire where expected  
P3-7| run every strategy through the lab on all available data; Book B on 2012-2026 daily (halves 2012-2018 / 2019-2026); Book A on whatever 1m depth P1 found (halves by date)| `docs/phase-reports/P3.md` with the gate table, by year, VIX tercile, results-season; mirror and random baselines; trials count; a plain-English verdict per strategy  
P3-8| Lab page on the portal| the owner can open each strategy's report on the phone  
  
The owner decides after P3 which strategies (if any) go to paper. "None of Book A passed" is an acceptable result. Book B alone is a valid outcome.

### P4: Paper trading on live data branch feat/p4-paper

Ticket| Work| Done when  
---|---|---  
P4-1| Wire the runner: stream, bars, enabled strategies, risk, order manager, PaperBroker; signals table incl. mirror/random rows| a full paper day with no errors; square-off leaves zero MIS  
P4-2| `engine/parity.py` \+ parity page| a replay of the same day matches the paper trades (fills within 0.05%)  
P4-3| Today / Signals / Books pages; Telegram messages and commands| the owner uses it on the phone for a week  
P4-4| run ≥ 6 weeks and ≥ 100 trades per enabled strategy| paper average R within the backtest's 80% interval; no unexplained parity faults for 2 weeks  
  
### P5: Live, small branch feat/p5-live

**Real money.** Before merging P5, Cursor and Claude post a written alert to the owner: "this enables real orders on Angel One, with capital X and risk Y". P5 is merged only after the owner's explicit written yes. `mode=live` and `live_orders=true` are set by the owner in `.env`, never by code.

Ticket| Work| Done when  
---|---|---  
P5-1| Angel order methods (place/modify/cancel/order book/positions/holdings) + order-update WS; tag lookup before retry| fake-server tests for each; the rejection message is surfaced  
P5-2| Static-IP self-check; live banner; first-2-weeks limits (1 position, risk 0.5%)| tests: IP mismatch turns on the kill switch  
P5-3| A one-share manual smoke test (owner present): LIMIT buy far below market, check it is visible on the Angel app, cancel it| order seen and cancelled; events logged  
P5-4| `scripts/export_tax.py`: CSV per FY (intraday speculative / delivery STCG/LTCG, costs split)| matches the trades table totals  
P5-5| Live run: 30 trades| execution cost within +0.03% of the paper model; parity clean  
  
### P6: Scale and learning

After 500+ labelled trades: port Part B's dataset, evaluation gate, meta-labelling (sizing by score) and RAG memory to this project. Raise capital only on the evidence.

## A17. AGENTS.md (verbatim) and Cursor prompts

### A17.1 AGENTS.md: copy into the repo root
    
    
    # Rules for AI coding agents (Cursor, Claude) - read fully before every task
    
    Project: NSE equity engine on Angel One SmartAPI. Source of truth: docs/PLAN.md. Decisions: docs/DECISIONS.md.
    
    1. Work on a branch feat/<phase>-<topic>; open a PR; never push to main; never deploy during
       market hours (Mon-Fri 09:00-15:45 IST).
    2. No secrets anywhere in code, tests, fixtures, logs, commits or chat. Keys come only from .env as SecretStr.
       Strip tokens from recorded fixtures.
    3. Every change has a test that fails before and passes after. `ruff check .` and `pytest -q` green before review.
       Tests never touch the network.
    4. Real orders require settings.mode == "live" AND settings.live_orders == True. Both default to off. Never change
       these defaults; never set them in code or tests. Any change that can send a real order must be called out at the
       top of the PR description in capital letters.
    5. Strategies, costs and risk are pure functions shared by the backtester and the live engine. No duplicate logic.
    6. Research results come only from lab/evaluate.py and are counted in lab/ledger.py. Never tune on the full history
       and report the same history. Changing a rule after seeing results is a new trial, flagged post-hoc.
    7. Store times as UTC epoch ms; schedule and display in IST (Asia/Kolkata). No naive datetimes.
    8. Round order prices to the instrument tick size. Use LIMIT / STOPLOSS_LIMIT orders only. Throttle orders to 5/s.
    9. Plain-English docstrings that say WHY (cite the plan section). Small functions. Match existing style.
    10. The service must stay under 600 MB RAM. No heavy ML libraries on the server.
    11. If something in docs/PLAN.md is unclear or seems wrong, stop and ask the owner; record the answer in
        docs/DECISIONS.md with the date.
    12. End every phase with docs/phase-reports/Pn.md: what was built, tests, acceptance numbers, open questions.
    

### A17.2 Prompts to paste into a new Cursor chat (one per phase)
    
    
    [P0] Read AGENTS.md and docs/PLAN.md fully (sections A1-A17). Create branch feat/p0-foundation and implement
    tickets P0-1 .. P0-8 from section A16 exactly. Use the layout in A5, the settings in A6, the tables in A7.1 and the
    deploy/systemd files in A14. Do not implement any broker calls yet. Write tests for every ticket, run ruff and pytest,
    then write docs/phase-reports/P0.md and open a PR. Ask me before deviating from the plan.
    
    [P1] Read AGENTS.md and docs/PLAN.md (A2.4, A6, A7, A8, A12, A15, A16-P1). Branch feat/p1-data. Implement P1-1 ..
    P1-7. Record real API responses ONCE into tests/fixtures/angel with all tokens removed (I will run the recorder on the
    server). Never commit keys. The report must show the 1-minute history depth Angel returns per symbol.
    
    [P2] Read AGENTS.md and docs/PLAN.md (A2.1, A9, A10 interface, A11, A15, A16-P2). Branch feat/p2-core. Implement
    P2-1 .. P2-7 with the exact test vectors in A2.1. The backtester must use the same strategy/risk/cost/paper-broker
    objects as the live engine.
    
    [P3] Read AGENTS.md and docs/PLAN.md (A10, A11, A16-P3). Branch feat/p3-research. Implement S1..S6 exactly as written
    (no parameter changes), run the lab on all data, and write docs/phase-reports/P3.md with the gate table and a
    plain-English verdict per strategy. Count every run in the ledger.
    
    [P4] Read AGENTS.md and docs/PLAN.md (A9, A12, A13, A16-P4). Branch feat/p4-paper. Wire the paper engine end to end
    on live data, parity job, portal pages and Telegram. Only strategies the owner enabled after P3.
    
    [P5] Read AGENTS.md and docs/PLAN.md (A3, A8, A9.4, A12.3, A14, A16-P5). Branch feat/p5-live. THIS PHASE CAN SEND REAL
    ORDERS. Implement P5-1 .. P5-4 behind mode=live AND live_orders=true. Put the real-money warning at the top of the
    PR. Do not set either flag anywhere.
    

## A18. Risks and disadvantages

#| Risk| Impact| Mitigation  
---|---|---|---  
1| No intraday edge after costs (the likeliest outcome: SEBI's 7 in 10; owner's crypto intraday was a coin flip)| Book A never goes live| Book B in parallel; pre-registered gates; mirrors/random baselines; accept "no" as an answer  
2| Cost drag at small size (A2.1)| ₹25k intraday loses 0.3-0.6R a trade to costs| min_position ₹1L, stops 0.8-1.5%, Book A live only with ₹50k+  
3| Short free 1m history| intraday research delayed| record from day one; daily data for Book B; paid feed is the owner's call  
4| Angel API reliability (rate limits AB1021, outages)| missed entries / exits| throttle, retries for reads, exchange-side stops, 15:05 square-off, reconcile, alerts  
5| Regulation changes (static IP, 2FA, Algo-ID)| engine cannot trade| all broker specifics isolated in broker/angel.py; Telegram TOTP fallback  
6| Server in Sydney; shared with the crypto engine| ~150 ms latency; one outage hits both; possible IP-location rejection| 1m-bar strategies only; MemoryMax; move to ap-south-1 if Angel rejects the IP  
7| Gaps and circuit locks| cannot exit MIS; stop slips| Nifty 100 only; circuit buffer; small size; no entries on results days  
8| Survivorship bias (today's Nifty 100 in old data)| backtests look better than reality| keep a constituents history file from NSE index-change notices; label results  
9| Taxes and accounting| speculative income needs ITR-3; CA cost| tax export from P5; owner's CA  
10| AI-built code quality / drift from the plan| subtle bugs with real money| AGENTS.md; Claude reviews every PR; phase gates; tests per change  
11| Over-trading many signals| costs grow, correlated losses| one position per symbol; max open limits; daily loss limit  
12| Recorded data loss (cannot be re-downloaded)| research history lost| nightly backups + monthly copy to the Mac  
  
## A19. Owner checklist, and how to test the Angel API key

### A19.1 What the owner does (outside code)

  1. AWS: give the EC2 an Elastic IP (or confirm 52.62.37.4 already is one). Tell Claude, because SSH and deploy settings follow the IP.
  2. SmartAPI "Add App": the values in A3. Enable TOTP. Keep the API key, secret and TOTP secret out of chat and out of Cursor.
  3. Create the private repo `dhruvparekhdp/nse-engine`; give Cursor access; add the deploy secrets (A14.1).
  4. Create a Telegram bot with @BotFather for this project, and note your chat id.
  5. Take screenshots of Angel's brokerage calculator: intraday ₹25k and ₹1L buy+sell, and delivery ₹50k buy+sell (for the P2 cost tests).
  6. Verify the 2026 NSE holiday list Cursor writes in P0-3.
  7. At each phase gate: read `docs/phase-reports/Pn.md`, ask Claude for the review, then merge.



### A19.2 Testing the Angel API key (read-only: no orders)

Run this on the Mac first; if login is refused for the IP, run it on the EC2. Make a separate folder and venv:
    
    
    mkdir -p ~/angel-test && cd ~/angel-test && python3 -m venv .venv && .venv/bin/pip install -q smartapi-python pyotp logzero websocket-client

Load the four values into this terminal only (input hidden, kept out of shell history):
    
    
    read -s "ANGEL_API_KEY?API key: " && echo && read -s "ANGEL_CLIENT_CODE?Client code: " && echo && read -s "ANGEL_PIN?MPIN: " && echo && read -s "ANGEL_TOTP_SECRET?TOTP secret: " && echo && export ANGEL_API_KEY ANGEL_CLIENT_CODE ANGEL_PIN ANGEL_TOTP_SECRET

Save as `~/angel-test/test_angel.py`:
    
    
    """Read-only SmartAPI check: login, profile, funds, one price, one day of 1-minute bars. Places no orders."""
    import os
    from datetime import date, timedelta
    import pyotp
    from SmartApi import SmartConnect
    
    key, code = os.environ["ANGEL_API_KEY"], os.environ["ANGEL_CLIENT_CODE"]
    api = SmartConnect(api_key=key)
    s = api.generateSession(code, os.environ["ANGEL_PIN"], pyotp.TOTP(os.environ["ANGEL_TOTP_SECRET"]).now())
    print("1 LOGIN :", s.get("status"), s.get("message"), s.get("errorcode"))
    if not s.get("status"):
        raise SystemExit("login failed - see the message above")
    p = api.getProfile(s["data"]["refreshToken"])
    print("2 PROFILE:", p.get("status"), "| exchanges:", (p.get("data") or {}).get("exchanges"))
    f = api.rmsLimit()
    print("3 FUNDS  :", f.get("status"), "| available cash:", (f.get("data") or {}).get("availablecash"))
    q = api.ltpData("NSE", "SBIN-EQ", "3045")
    print("4 PRICE  :", q.get("status"), "| SBIN last price:", (q.get("data") or {}).get("ltp"))
    d = date.today() - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    c = api.getCandleData({"exchange": "NSE", "symboltoken": "3045", "interval": "ONE_MINUTE",
                           "fromdate": f"{d} 09:15", "todate": f"{d} 15:30"})
    rows = c.get("data") or []
    print("5 BARS   :", c.get("status"), c.get("message"), "| 1-min bars for", d, ":", len(rows), "| first:", rows[0] if rows else None)
    api.terminateSession(code)
    print("done - logged out")
    
    
    
    cd ~/angel-test && .venv/bin/python test_angel.py

**Good result:** lines 1-4 show True, and line 5 shows about 375 bars (0 on a holiday).

**Common failures:**

  * "Invalid TOTP": the 6-digit code was used instead of the secret text, or the Mac's clock is off.
  * An API key or IP error: run it on the EC2.
  * AB1021: wait a minute and run again.



# Part B: Machine learning + RAG memory for the Crypto Signal Engine

For Cursor working in the existing public repo `crypto-signal-engine` (Python, aiohttp portal, APScheduler, Postgres via asyncpg, deployed to the same EC2 by GitHub Actions on every push to `main`). Cursor has no chat context, so everything needed is below.

## B1. Why, and what the evidence already says

The owner wants the system to learn from its own past (ML + RAG), and wants this to be a learning journey. Each phase starts with a one-page lesson (`docs/learn/NN-*.md`) and ends with one command the owner runs and 3-5 check questions. LLM use: free Groq/Gemini tiers first; the Claude API only after retrieval proves useful, with a monthly cap.

Book| Evidence (measured)| Verdict  
---|---|---  
Swing (live on Delta India, ₹500)| 3,487 trades 2021-26, 12 coins; win 49.7%, avg win +1.53R, avg loss −0.82R, **+0.35R a trade after fees** ; every year positive (2022 +0.18, 2023 +0.29, 2024 +0.47, 2025 +0.33, 2026 +0.43)| the only proven edge  
Intraday signals| walk-forward AUC 0.52; 5m-8h direction 45-50%| coin flip  
AI judging trades| LLM gate AUC 0.50; using only its picks cut total R from +60 to +19| never helped  
News sentiment| market-news score followed BTC's 24 h move exactly (22 Oct, 48/48)| echoes price  
Channel bracket (paper)| 78% "in profit" but −1.04% a trade (one full stop = 50 small wins)| geometry, not edge  
Options: selling volatility| Deribit DVOL vs the next 30 days' realised volatility 2022-26: BTC implied above realised on 69% of days (+5.2 vol pts), ETH 62% (+1.7); next-day sellers beat the move on ~70% of days; worst day 7.3x (BTC) / 7.7x (ETH) the priced move| real premium, dangerous tail  
Volatility model (past volatility + implied)| as a forecast it is worse than implied itself (error 0.144 vs 0.114 BTC); "sell only when the model says ≥ 3 pts rich" gives +8.6 pts on 46% of days vs +5.2 always (BTC); ETH: no signal; buying always lost| useful only as a sell filter for BTC  
  
**What a gain is worth, and what can be proven:**

  * One swing trade's result has a standard deviation of 1.44R. About 40% of trades come in 3+ coin clusters, so the 3,487 trades are only about 1,600 independent bets.
  * Proving +0.05R a trade needs about (1.44 / 0.05)2 ≈ 830 independent trades per version. That is 1-2 years of backtest, and about 8 years of live trading at ~8 live trades a month. So small gains can only be accepted from walk-forward backtests plus all-coin paper.
  * Value at 3% risk: +0.05R ≈ +1.2% of the wallet a month (₹12 on ₹1,000). Wallet size matters more: in the simulator, ₹500 grew x1.48 in 2021-24 while ₹1,000 grew x7.6.



## B2. Rules for Cursor in this repo

  * Branch `feat/ml-<phase>`; PR; **never push`main`** (it auto-deploys to production). Claude reviews, the owner merges.
  * Every change has a test that fails before and passes after; the full `pytest -q` is green (about 1,900 tests).
  * No code that places, sizes or changes live orders. Never read or print API keys. The repo is **public** : no secrets, no production data in git (`data/` is git-ignored).
  * Production DB is read-only; back up before any schema change; never DROP/DELETE/TRUNCATE.
  * Match the style: plain-English docstrings citing the owner's ask and date; structured `log.info` events; numpy inference on the server from JSON model files (as `analysis/models/headline_triage.json`).
  * The server is a t3.small with 2 GB RAM: training runs on the Mac/ThinkPad; nothing on the server loads more than ~100 MB.
  * Every model run goes through `analysis/ml/evaluate.gate()` and the lab ledger (`analysis/lab/ledger.py`). No hand-picked results.



## B3. Existing pieces to reuse (paths in the repo)

Piece| Where  
---|---  
Training pattern (numpy, 5 rolling time splits, write the model only if it beats the baseline)| `scripts/train_headline_triage.py`, `analysis/headline_triage.py`  
Point-in-time indicators| `analysis/lab/features.py`; side-signed features in `scripts/edge_research.py` (`features()`), `scripts/signal_replay.py`  
Labelled history| `data/lab/live_sim_trades.pkl` (swing trades), `data/lab/signal_replay/replayed.parquet` (1,768 intraday signals), `data/lab/edge_features.parquet`, `data/lake/` (Binance bars + funding)  
Live simulator| `scripts/live_sim.py` (`simulate(...)` with the real sizing code)  
Embeddings| bge-small through the HF Space: `collectors/hf_space.py`; cosine in `analysis/headline_dedupe.py`; vectors currently thrown away in `collectors/hermes.py`  
LLM router| `collectors/llm_client.py` (per-role fallback chains, budgets, call log); post-trade lessons in `scripts/llm_review_v2.py`; tables `signal_reviews`, `market_briefings`, `news_sentiment`, `event_precedents`  
Options paper book| `analysis/vol_book.py`, job `_vol_paper_job` in `scheduler/runner.py`, `/api/vol`  
AI rules and the forecast sketch| `docs/AI_REVAMP_PLAN.md`, `design/7d_forecast_plan.md` (k-nearest past setups)  
  
## B4. Phases and tickets

### B-P0: one labelled dataset

  * **Lesson:** `docs/learn/00-data.md` (labels, features, point-in-time data, leakage; our own example: `llm_review` v1 looked one bar ahead).
  * **Build:** `analysis/ml/dataset.py`: 
    * `build_swing()`, `build_intraday()`, `build_bracket()`, `build_vol()`;
    * every row has `decision_t` (ms), `known_t` per feature group, `cluster_id` (same bar + side), labels (`r_net`, `win`, `mfe_r`, `mae_r`) and `period` ("2021-24" / "2025-26");
    * outputs to `data/ml/*.parquet` plus a generated `docs/learn/dataset_card.md`.
  * **Tests:** no feature with `known_t` after `decision_t`; cluster grouping; row counts equal the sources.
  * **Owner command:** `python -m scripts.ml dataset`.



### B-P1: evaluation harness

  * **Lesson:** `01-evaluation.md` (walk-forward, embargo, AUC/Brier/calibration, R after fees, multiple testing, the sample-size maths in B1).
  * **Build:** `analysis/ml/evaluate.py`: 
    * `walk_forward(df, fit, predict, by="year", embargo_days, group="cluster_id")`;
    * `baseline_scores(df)`;
    * `gate(result)`: beats the baseline in both periods with ≥ 30 trades per fold;
    * `report(result)`;
    * every call logged in the ledger.
Add `scikit-learn` and `lightgbm` to `requirements-dev.txt` only (offline).
  * **Tests:** shuffled labels fail the gate; a planted feature passes.



### B-P2a: options volatility (first model)

  * **Lesson:** `02-volatility.md`.
  * **Build:**
    1. `scripts/ml_vol_backtest.py` reproduces B1's table from Deribit DVOL (public `get_volatility_index_data`, cached in `data/lake/dvol/`) and `load_bars`. It must match within ±0.5 pt.
    2. An hourly Delta chain snapshot to `data/vol_chain/YYYY-MM-DD.jsonl` (ATM IV per expiry, 25-delta skew, straddle spread) inside the existing vol job.
    3. `analysis/ml/vol_forecast.py`: a regression of next-day/next-week realised volatility on implied volatility + 1/7/30-day realised volatility + funding. It is exported to `analysis/models/vol_forecast.json` only if the gate passes.
    4. Two new paper books in `analysis/vol_book.py`: 
       * "sell + wings" (an iron fly: short ATM straddle + long wings at ~1.5x the expected move);
       * "ML-gated sell + wings" (sells only when the forecast is ≥ 3 vol pts below implied).
Both report worst day and worst week.
  * **Keep or kill** after ≥ 40 daily expiries: the gated book beats always-sell + wings on average and on worst week, and Delta's own premium is positive after spread and fees.



### B-P2b: swing meta-label sizing (shadow only)

  * **Lesson:** `03-meta-labelling.md`.
  * **Build:** `analysis/ml/meta_label.py` scores P(win) and expected R (logistic regression, then LightGBM if it passes the gate). `scripts/live_sim.py` gets a `risk_fn(trade) -> pct` hook to compare flat 3% with 2/3/4% by score tercile at ₹500 / ₹1k / ₹2k.
  * **Keep** only if both the median and the worst 3-month window improve in both periods, and the AUC confidence interval's lower bound is above 0.5.



### B-P2c: regime labels

  * **Lesson:** `04-unsupervised.md`.
  * **Build:** `analysis/ml/regime.py`: k-means / Gaussian mixture on BTC 30-day volatility, 50/200-day trend and funding, refit yearly. It is a label on every report, not a filter.



### B-P3: RAG memory

  * **Lesson:** `05-rag.md`.
  * **Build** `analysis/rag/`: 
    * `cards.py`: one case card per closed trade, signal or straddle: facts as text and numbers, the outcome, and the lesson from `signal_reviews` / `llm_review_v2`. Headlines and briefings are added, keeping their bge-small vectors.
    * `store.py`: a float16 numpy matrix plus a parquet of metadata in `data/rag/`. Sizes: ~4k cards ≈ 3 MB; news ≈ 0.3 MB a day; keep 180 days hot (~55 MB).
    * `retrieve.py`: `similar_setups(features, k=30)` (feature kNN, past cases only) and `similar_text(query, k)`.
    * `ground.py`: a prompt with the card ids, sent through a new `rag_note` role in `collectors/llm_client.py` (free chain). Code checks every number and id in the answer against the cards and drops the note on any mismatch.
  * Shown on the Signals page and in the trade notes, as information only.
  * **Keep or kill:**
    * the kNN win rate needs AUC ≥ 0.55 out-of-sample in both periods, otherwise it is shown as "history" with no score;
    * notes must pass the faithfulness check ≥ 95% of the time, and the owner rates 10 a week.



### B-P4: self-learning loop

  * **Lesson:** `06-mlops.md`.
  * **Build:**
    * a nightly job turns new closed trades into dataset rows and cards;
    * `data/ml/registry.json` holds the model registry;
    * a monthly offline retrain (`scripts/ml_retrain.py`) promotes a challenger only if the gate passes and 30 days of shadow results are not worse;
    * automatic demotion;
    * drift alerts (PSI > 0.25);
    * a System → Learning page.



### B-P5 (later)

A research agent proposes hypotheses from the ledger (counting trials). Later, distil a small local model from logged prompts and answers (`finetune/` exists).

## B5. Risks

  1. Overfitting and data snooping: hundreds of trials already, so use the ledger and both-period gates.
  2. Leakage: `known_t` tests.
  3. Small clustered samples: group by `cluster_id`.
  4. Regime change: BTC's volatility premium was about 0 in 2026, so report by year.
  5. Options tail: 7-8x days, so only wing-capped books.
  6. Slow feedback: ~8 live labels a month.
  7. A 2 GB server: offline training.
  8. Free-tier quotas and LLM errors: code-checked notes.
  9. Automation risk: nothing touches live without the owner's explicit yes.
  10. Delta's IV differs from Deribit's, so use our own chain history.



## B6. Prompt for Cursor (crypto repo)
    
    
    Read docs/ML_RAG_PLAN.md (Part B of the plan PDF) fully. Work on branch feat/ml-p0. Implement phase B-P0
    (analysis/ml/dataset.py, docs/learn/00-data.md, scripts/ml.py dataset, tests/test_ml_dataset.py). Follow B2 rules:
    never push main, no live-order code, no secrets, tests that fail before and pass after, full pytest green.
    Then stop and write a short report with row counts and base rates per period.
    

End of document. Questions go to the owner; decisions go to docs/DECISIONS.md.
