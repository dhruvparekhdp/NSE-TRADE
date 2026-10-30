# CURSOR NEXT: everything not built yet (written by Claude; updated 29 Oct 2026)

Read `AGENTS.md` first, every time. Paper only: nothing here may send an order, and `mode` / `live_orders` are never
touched. One branch per ticket group, one PR each; Claude reviews every branch and does every server deploy. Never
deploy, never push `main`. Tests never touch the network; recorded fixtures have tokens stripped.

## Where things stand (29 Oct 2026)

**Server runs:** `deploy/20261026` = e59c72c + four fixes (5f0939f cooldown, 5c7e3cd vol rank / 200-DMA cards,
6af5950 NSE pre-open parser + key, be3bdc9 news fetch + dedupe). `STRATEGIES_ENABLED=["S6_swing","S6b_keltner"]`,
paper. **Your `feat/v8-complete` has C0 but NOT those four fixes**, so deploying it as is would undo them (C11).

**Claude's stopgaps on the server** (reference copies in `scripts/stopgap/`; each is replaced by a ticket below):
| Stopgap (server path) | What it does | Started by | Replaced by |
|---|---|---|---|
| `var/ws/ws_recorder.py` | Angel WebSocket (QUOTE mode) for 100 stocks + NIFTY 50 / BANK / VIX; 1-min bars to `var/ws/bars_1m_<date>.jsonl`; writes `var/quotes_cache.json` every 5 s (portal ticker, Watchlist, Nifty card) | cron 09:05 IST Mon-Fri | C6 + C1 |
| `var/ws/live_signals.py` | Book A strategies every minute on those bars; first signal per strategy x symbol into `signals` (book A, decision `shadow`) | cron 09:16 IST Mon-Fri | C6 + C12 |
| `backfill_nse_chart.py` / `backfill_today.py` | rebuild missing morning bars (NSE chart JSON, price only) / Angel 1-min candles | by hand | C6 + C10 |
| `set_mpin.py` | save a key over SSH with a hidden prompt (`save_key`) | by hand | C9 |
The two cron lines carry the comment "remove when ticket C6 lands". Removing them is part of C6's acceptance.

**Known facts from running live (26-29 Oct):**
- Angel's candle API refuses 1-minute history for this account ("Access denied because of exceeding access rate")
  since 26 Oct, even at 1 request / 4 s; ONE_DAY for the 16:10 job works. WebSocket and quote API work. Parallel
  sessions are allowed. A wrong MPIN 5 times locks the account (AB1007); 28 Oct reached attempt 4 (C9).
- NSE file/JSON sources that work from the server: UDiFF bhavcopy zip, pre-open `key=FO` / `key=NIFTY%2050`
  (`key=NIFTY` is dead), intraday `api/chart-databyindex-dynamic?index=<SYM>EQN&type=symbol` (timestamps are IST
  written as UTC epoch: subtract 5 h 30 m). Moneycontrol + Economic Times RSS work.
- No paper trade has opened yet: Book A is shadow by design (no intraday paper execution exists, C12); every Book B
  pick (16 on 26-28 Oct) was blocked by F1 (Nifty vol rank 0.85 > 0.667) although all 16 pass sizing; the portal
  shows "FILTER OFF" because the `market_filter` setting is not wired into the scan (C13).

## Order (inside a group, tickets can go in any order)

| # | Group | Branch | Why |
|---|---|---|---|
| C11 | Bring the four deployed fixes into your line | `feat/v8-complete` | otherwise the next deploy undoes them |
| C17 | Paper book correctness (limits, one position per stock, cash, job order) | `feat/c17-paper-book` | replay 30 Oct: 6 positions with limit 4, DRREDDY bought twice, wallet never debited |
| C13 | Wire `market_filter` into the scan; truthful badge | `feat/c17-paper-book` (same branch as C17: both change `job_scan`) | portal says FILTER OFF while F1/F2 block everything |
| C6 | Live Angel WebSocket inside the engine | `feat/v8-live-1s` | retire the recorder + signal stopgaps; Book A on live bars from 09:15 |
| C12 | Book A paper execution (intraday) | `feat/c12-book-a-paper` | owner wants paper trades from the intraday signals |
| C1 | Quotes from the engine's own feed | `feat/c1-quotes` | Watchlist / ticker today come from the stopgap file; Yahoo still overwrites it every 5 min |
| C9 | Secure key entry (HTTPS / CLI) + stop repeated bad logins | `feat/c9-keys` | Keys page cannot save over plain HTTP (403 by design); MPIN reached 4/5 |
| C10 | Market data store: 365 days in DB, older to JSON; files first | `feat/c10-store` | owner 26 Oct; candle API blocked |
| C14 | Opening data: pre-open Nifty IEP, opening scorecard, GIFT Nifty | `feat/c14-opening` | Market mood opening cards are empty |
| C15 | Signal outcomes for Book A shadow + Evidence | `feat/c15-outcomes` | Signals page OUTCOME column is empty for Book A |
| C16 | Ops: health truth, Yahoo removal, Angel throttle, alerts | `feat/c16-ops` | Health shows "login false / WS off" while data flows |
| C2 | Global cues source | `feat/c2-cues` | cues show stale; GIFT Nifty has no source (C14 uses it) |
| C3 | Event calendar + RBI date bug | `feat/c3-events` | `policy_dates.json` has 2025 RBI dates labelled 2026 |
| C5 | Lab diagnostics (signal why and movement) | `feat/c5-diagnostics` | Evidence page needs why / MFE / MAE / R at horizons |
| C4 | Minute history import | `feat/c4-history` | recorder files since 26 Oct are the only clean 1-min history |
| C8 | Strategy rework after the backtests | `feat/c8-rework` | no strategy passes; new pre-registered trials |
| C7 | News history (GDELT) for the event study | `feat/v8-event-study` | V8-P3 needs headlines back to 2020 |
| V9 | Options on news + delta-hedged vol book | `feat/v9-options` | `docs/PLAN_V9_OPTIONS.md` |

## C11. Bring the deployed fixes into `feat/v8-complete` (first)

Merge (or cherry-pick) `origin/deploy/20261026` commits 5f0939f, 5c7e3cd, 6af5950, be3bdc9 into `feat/v8-complete`.
Files: `web/test_angel.py`, `data/nse_http.py`, `web/portal_data.py`, `data/preopen.py`, `news/scrape.py`,
`engine/runner.py` (job_news), tests `test_test_angel.py`, `test_nse_http_warm.py`, `test_portal_market_filters.py`,
`test_preopen_nse_shape.py`, `test_news_fetch_dedupe.py`, fixture `tests/fixtures/nse_preopen_fo_20261026.json`.
Acceptance: all those tests pass on your branch; `git diff origin/deploy/20261026 -- <those files>` shows only your
additions; `pytest -q` / `ruff check .` green. Also open the PR for `fix/monotonic-cooldown` -> main (CI has failed on
main since 24 Oct for that reason).

## C17. Paper book correctness (do with C13 on one branch, `feat/c17-paper-book` cut from `feat/v8-complete` after C11; both are needed before the first paper trade)

Found 30 Oct 2026 by replaying the engine's own `job_eod_fill` + `job_scan` for 26-29 Oct on a copy of the server's
`engine.db` and daily lake (`scripts/stopgap/replay_paper.py`). With the filter ON it reproduces production exactly
(26 picks, all `market_filter_f1_vol`, 0 trades). With F1/F2 OFF:
```
26 Oct  picks=6  decisions={'pending': 6}
27 Oct  fills=6  (TECHM 12, TCS 8, DRREDDY 16, DRREDDY 16, HCLTECH 15, WIPRO 107)  then max_open_swing blocks everything
holdings: 5 symbols (DRREDDY 32 shares), trades 6, wallet 100,000.00
```
Bugs (each needs a failing test first):
1. **max_open_swing (4) not enforced inside one scan.** `job_scan` loads `PortfolioState` once; queued pending orders
   do not count, so 6 were queued and filled. Count pending + open, and increment the state as each order is queued.
2. **Same stock twice.** S6_swing and S6b_keltner both picked DRREDDY -> two orders, 32 shares. One open-or-pending
   position per symbol (first strategy in a fixed order wins; the other is logged `skip_reason="already_in_symbol"`).
3. **Cash never debited.** `_bump_wallet` runs only on exits (line ~228), so ₹1.19 L of stock was bought from a ₹1 L
   wallet that still reads ₹1,00,000, and the portal's equity (wallet + held value) double-counts. Debit cost + buy
   charges at fill, credit proceeds - charges at exit; refuse a fill without enough cash (`skip_reason="cash"`).
   Equity = cash + marked holdings.
4. **Job order race.** 29 Oct: `job_daily_bars` (16:10) finished at 16:15:15, after `job_eod_fill` (16:15:00) ran. Make
   fill and scan wait for today's bars (run them as one chain after daily bars, or check the bar date and retry).
Acceptance: the replay with the filter off ends with ≤ 4 holdings, no duplicate symbol, cash + holdings = ₹1 L +/-
costs, and every skip has a reason; with the filter on it is unchanged.

## C18. Merge `fix/runtime-overrides` (0034a49) into `feat/c17-paper-book` (first)

Deployed 30 Oct 2026. `apply_db_secrets()` wiped the SQLite runtime settings on every engine start (kill_switch
included). Test `tests/test_secrets_loader_overrides.py`. Also see DECISIONS 2026-10-30 (paper with the filter off).

## C13. Wire the `market_filter` setting into the scan

`engine.paper_jobs.job_scan` applies F1/F2 unconditionally, while `/api/portal/meta` reports
`get_setting("market_filter", "off")` and the portal shows FILTER OFF.
- `market_filter`: `"on"` (default; PREREG rule) | `"off"` (paper only: picks are taken, and each records
  `would_skip_reason` = the F1/F2 reason so the two regimes can be compared later) | `"shadow"` (no trades).
- Validation: `off` is refused when `mode == "live"`.
- Badge shows the real state; Settings page can change it (runtime override, audited).
- Tests: on/off/shadow decisions on a fixture lake; `would_skip_reason` stored; live + off refused.

### C8. Strategy rework after the backtests (`feat/c8-rework`, after C5)

Backtests (`docs/research/BACKTEST_2020_2026.md`): Book B works only in 2020-23 (second half ≈ 0 R); every Book A
strategy loses after costs in FY 2025-26 and FY 2026-27, and none beats a random entry. Do not tune these on the same
history. New pre-registered trials in `docs/PREREG.md`, each a ledger entry:
- Book A cost floor: reject any signal whose round-trip cost exceeds 0.25 R (MIS round trip ≈ 0.14% of notional, so
  the stop must be ≥ 0.56%); report how many signals survive per strategy.
- Book B regime gate on trend strength (Nifty 50-day slope and breadth above the 50-day average) in place of F1/F2.
- Paper book on the server: the owner decides whether to set `STRATEGIES_ENABLED=S6_swing,S6b_keltner` (paper,
  filters on) to test the scan -> fill -> outcomes plumbing on live days. It is not evidence of an edge.

---

### C9. Secure key entry (`feat/c9-keys`, do soon)

26 Oct 2026: the owner reset the Angel MPIN; the Keys page returned 403 because `require_secure_channel` (R3)
refuses secret saves over plain `http://52.62.37.4`, and Test Angel is refused the same way. Claude saved it with a
one-off SSH script (hidden prompt -> `config.secrets_loader.save_key`) and restarted nse-engine after 15:45.
- `scripts/set_key.py <key>`: hidden prompt twice, validates per field (MPIN 4 digits, TOTP base32, ...), calls
  `save_key`, prints the masked value + fingerprint; documented in `docs/RUNBOOK.md` with the SSH one-liner.
- The engine must pick up a changed key without a restart: `_ensure_login` re-reads DB secrets (cheap) before
  each login attempt, and records which fingerprint it used.
- Login failures must stop early: after 2 consecutive AB1007 "INVALID MPIN" today, skip further automatic login
  attempts until the key changes (5 bad tries lock the account; 26 Oct burned attempts 2-4 at 08:45-08:55).
  Show the state on Health.
- HTTPS for the portal (owner chooses: a domain + Let's Encrypt in nginx, or Tailscale). Until then the CLI is the
  supported path; the Keys page should say so instead of a bare 403.
- Tests: CLI validation, re-read on login, the AB1007 stop rule.

### C10. Market data store and sources (`feat/c10-store`; owner, 26 Oct 2026)

Owner: "use socket and start storing new data ... other sources to get direct json or excel data, instead of api ...
only keep 365 days data only in db, other data shifts to json file automatically".
Why: on 26 Oct Angel refused every candle-history request for the account ("Access denied because of exceeding access
rate", after the weekend history downloads), while its WebSocket and quote API kept working. The engine must not
depend on the candle API for anything it can get from a file.

**Sources (files first, APIs second)**
| Data | Primary source | Fallback |
|---|---|---|
| Daily OHLCV + delivery, all NSE equities | NSE CM UDiFF bhavcopy zip, `nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_<YYYYMMDD>_F_0000.csv.zip` (works from the server; `data/history.parse_bhavcopy_zip`) | Angel ONE_DAY |
| Index closes (Nifty 50, Bank, VIX) | NSE daily index close file in the archives (find the current URL; record it in DECISIONS) | NIFTYBEES from the bhavcopy (already used by `nifty_closes`) |
| F&O (for V9) | NSE F&O UDiFF bhavcopy | none |
| Live intraday | Angel WebSocket (C6) | Angel quote API, 1 call/s |
| 1-min history gaps | Angel candle API after the close only: ≤ 1 request/s, stop on the FIRST rate error, never during market hours | none |
| Pre-open, corporate actions, bulk/block deals, FII/DII | NSE JSON / CSV files from the archives | none |
Bhavcopy appears around 18:00 IST; the EOD scan moves to after it (or runs at 16:20 on Angel and re-runs when bhav arrives,
bhav wins on conflicts as `Lake.write_daily` already prefers it).

**Storage: hot 365 days in the DB, older automatically to JSON**
- DB (Postgres, already on the box): `bars_1d(symbol, date, o,h,l,c,v, delivery, source)` and
  `bars_1m(symbol, ts_ms, o,h,l,c,v, ticks, source)` partitioned by month; UTC epoch ms (plan rule 7).
- Nightly 19:30 IST `job_archive`: rows older than 365 days -> `var/archive/<tf>/<SYMBOL>/<YYYY-MM>.jsonl.gz`
  (one JSON object per bar, gzip), verify row count + checksum, then delete from the DB in the same transaction.
  Idempotent; never archives the current month; logs counts on Health.
- `data/store.py: read_bars(symbol, tf, start, end)` reads DB + archive transparently; backtests and the live engine
  use it (plan rule 5). The parquet lake becomes an import source only.
- Size: 1-min bars ≈ 101 instruments x 375 x 250 ≈ 9.5 M rows/year in the DB; gzip JSON ≈ 200 MB/year archived.
  Raw ticks are NOT stored (about 3 M/day); optional 1-second bars kept 5 days, never archived (owner decides).
- Import on day one: Claude's `var/ws/bars_1m_<date>.jsonl` (recorder started 26 Oct 13:17), the backfilled lake
  (`var/lake/bars_1d`, NSE bhav 24 Jun 2025 -> 23 Oct 2026), and later `var/bt/` Angel history files.
- Tests: archive move + verify + delete, reader across the 365-day boundary, idempotent re-run, a crash between
  write and delete loses nothing, memory under the 600 MB cap.

## C0. Done (26 Oct, `5a70fe2` on `feat/v8-complete`): live login + portal hubs merged.

## C1. Quotes from the engine's own feed (replace the stopgap file and Yahoo)

Today `var/quotes_cache.json` is written every 5 s by the stopgap recorder (shape: `{ts_ms, source, quotes: [{symbol,
ltp, open, high, low, prev_close, volume, chg_pct, ts_ms, source}]}`; NIFTY / BANKNIFTY / INDIAVIX names) and Yahoo's
`job_free_quotes` still overwrites it with 20 names every 5 min. After C6, quotes come from the engine's WebSocket
ticks; the quote API below is the fallback when the socket is down.

- `engine/quotes.py`: `fetch_quotes(api, tokens) -> list[Quote]` using SmartAPI `getMarketData("FULL",
  {"NSE": [...]})`, at most 50 tokens per call, at most 1 call per second (plan rule 8 throttle spirit).
- Runner job every 60 s from 09:15 to 15:30 IST plus one at 15:35 (closing values), trading days only; uses the
  existing session (`_ensure_login`), never a second login.
- Table `quotes(symbol PK, ltp, open, high, low, prev_close, volume, change_pct, ts_ms, source)`; UTC epoch ms.
- `/api/watchlist` reads `quotes`; a row older than 3 min shows a "stale" badge; outside market hours show the last
  close with its time. Remove the Yahoo call from the Watchlist path (keep Yahoo nowhere on the server hot path).
- Tests: parser on a recorded fixture (tokens and JWT stripped), batching of 100 tokens into 2 calls, stale logic.
- Memory: the job must not hold more than one response at a time.

## C2. Global cues: a source that works from the server

Yahoo (429) and Stooq are blocked from the server; NSE's own APIs, NSE archives and Moneycontrol RSS work.
- Write `scripts/probe_cues.py` (run by Claude on the server, read-only) that tries, for GIFT Nifty, S&P 500 futures,
  Nasdaq, Dow, Nikkei, Hang Seng, DAX, FTSE, US 10Y, DXY, Brent, gold, USDINR: (a) Yahoo v7 quote with a crumb, ONE
  batched request, (b) CNBC quote web service, (c) NSE IX for GIFT Nifty, (d) any other free JSON source you find.
  It prints which source returns fresh data for which symbol. No paid source without the owner's OK.
- `data/cues.py`: a source chain per symbol from the probe result (recorded in `docs/DECISIONS.md` with the date);
  poll every 5 min 06:00-09:15 IST and every 15 min in market hours; one batched request per source per poll.
- When every source fails, Market mood shows "no source" and the time of the last good value, never stale numbers
  presented as current.
- Tests on recorded fixtures; the chain falls through on 429 / timeout / empty.

## C3. Event calendar, and fix the RBI date bug

- `config/policy_dates.json` lists RBI MPC dates 2026-02-07, 04-09, 06-06, 08-06, 10-01, 12-05. Those are the
  **2025** meetings. The 2026 meetings so far were 2026-02-06, 04-08, 06-05, 08-05 and 10-07 (hike).
- Replace it with `config/events.json` (Claude's draft is in this branch): RBI 2019-2026 with cut / hike / hold,
  FOMC 2021-2026 (federalreserve.gov), Union Budgets, election results, exit polls; times in IST; overnight events
  (FOMC) map to the next Indian session. Add US CPI and India CPI release dates 2020-2026.
- VERIFY every RBI date and decision for 2019-2024 against RBI press releases (Claude's draft has those from memory)
  and record the check in `docs/DECISIONS.md`.
- `data/events.py`: `events_on(day)`, `next_event(after_ms)`, used by Today, the BTST study and V9.
- Tests: loader, overnight mapping, the 2026 dates above.

## C4. Minute history import

The planned Angel history download was lost (Claude's scratchpad was wiped) and Angel now refuses 1-min candles for
the account. What exists:
- Daily: `var/lake/bars_1d/` on the server, NSE bhavcopy 24 Jun 2025 -> 23 Oct 2026 (`source="bhav"`) + the engine's
  own 16:10 Angel ONE_DAY bars since 26 Oct.
- 1-min: `var/ws/bars_1m_<YYYYMMDD>.jsonl` from the stopgap recorder since 26 Oct (26 Oct from 13:17; 27 Oct full;
  28 Oct from 11:54 plus `_backfill` morning rebuilt from NSE prices, `src` = `angel_hist` / `nse_chart_price_only`;
  29 Oct full from 09:05). One JSON object per bar: `{sym, ts (IST ISO), o, h, l, c, v, ticks, src}`.
- `scripts/import_recorder_jsonl.py`: load those files into the C10 store (dedupe on symbol + minute; keep `src`;
  mark `nse_chart_price_only` bars so backtests can exclude them).
- Angel 1-min backfill only after the close, ≤ 1 request / 4 s, stop on the first refusal; never in market hours.
- Survivorship: the universe is TODAY's Nifty 100; join `config/universe_history.csv` in every backtest report.

## C5. Lab diagnostics: why a signal fired and how price moved after it

Port Claude's scratch `book_a.py` diagnostics into `lab/diagnostics.py` (pure, reuses `build_intraday_context`,
`core.exits.step_exits`, `lab.backtest._close_bt`): per signal the strategy features (the "why"), MFE / MAE in R,
R at +15 / +30 / +60 min, R if held to the 14:55 square-off, net R after MIS costs, plus a mirror (opposite side,
same stop distance) and a random-minute entry in the strategy's window. Evidence page: a table of the last N signals
with those columns and a per-strategy summary (pick vs mirror vs random). Results still only count through
`lab/evaluate.py` + ledger (plan rule 6); diagnostics are labelled "diagnostic".

## V9. Options on news (BTST / STBT) + delta-hedged vol book

Everything is in `docs/PLAN_V9_OPTIONS.md` (tickets V9-1 to V9-6). Paper only. Claude adds the backtest numbers to
§2 when the runs finish; build V9-1 / V9-2 / V9-6 first (pure code), V9-4 only after V9-3's gate result.

## C6. Live Angel WebSocket inside the engine (retires both stopgaps)

Port `scripts/stopgap/ws_recorder.py` + `live_signals.py` into the engine (they are the working reference):
- Runner task from 09:05 to 15:31 IST on trading days: one SmartWebSocketV2 connection on the engine's own session
  (`_ensure_login`, never a second login), QUOTE mode, the universe + NIFTY 50 / NIFTY BANK / INDIA VIX.
- Ticks -> 1-s and 1-min bars (`BarBuilder1s` / `MultiBarFeed`); minute volume = change in the day's cumulative
  volume, first tick only sets the baseline; bars stored in the C10 store; quotes cache updated (C1).
- `job_book_a_shadow` runs the Book A strategies on every closed bar (logic identical to `live_signals.py`: first
  signal per strategy x symbol per day, skip a symbol until its bars start by 09:16, context from the previous
  session); decisions `shadow` or `pending` per `book_a_mode` (C12).
- Reconnect with backoff on drops (without re-login); if the session is lost, one re-login, then stop and alert.
- Health: `ws_connected`, last tick age, ticks/min, bars written; Command badge uses it.
- SIGTERM flushes the open minute (the stopgap learned that nohup jobs ignore SIGINT).
- RSS under 600 MB for a full session; soak test replays a recorded hour (from `var/ws/bars_1m_20261029.jsonl`) at 60x.
- Acceptance includes deleting the two NSE cron lines on the server (Claude does it at deploy).

## C12. Book A paper execution (intraday, MIS)

- `book_a_mode = "paper"`: each Book A pick becomes a paper MIS order filled at the NEXT minute's open + slippage
  (marketable limit rounded to tick, plan rule 8); at most `max_open_intraday` (3) open; no entry after 14:35.
- Exits every minute with `core.exits.step_exits` (stop, target, trail, time exit), square-off 14:55; costs from
  `core.costs` MIS; sizing via `core.risk.size` (₹1 L minimum notional, 1% risk).
- Same tables / wallet as Book B so the Paper wallet and Paper book show both books; a per-book P&L split.
- The backtests say every Book A strategy loses after costs: the Paper book page must show that plainly (net R, costs).
- Tests: fill at next open, stop hit inside a bar, square-off, max-open refusal, cost totals vs a hand-worked trade.

## C14. Opening data

- Pre-open Nifty: `key=NIFTY` is dead; compute index IEP / imbalance from the 50 constituents of `key=NIFTY%2050`
  (free-float weights from the NSE index file, or equal-weight with a label) so the Market mood card fills.
- Opening scorecard (gap, gap filled, 15-min OR, breadth, first-5-min volume vs 20-day, open type) from the 1-min
  bars (C6 / recorder files); it is empty today.
- GIFT Nifty: use the C2 source chain; show the % vs Nifty's previous close and its age.

## C15. Outcomes for Book A shadow signals

`job_outcomes` resolves Book B; Book A rows show "—". For every Book A signal compute, from 1-min bars: R at +15 /
+30 / +60 min, MFE / MAE, R held to 14:55, and the managed-exit net R (same as the backtest diagnostics, C5). Store
in an outcomes table keyed by signal id; Signals page OUTCOME column and Evidence summaries read it.

## C16. Ops

- Health: report the recorder/WebSocket state truthfully (today it says login false / WS off while data flows).
- Remove Yahoo from the server hot path (`job_free_quotes` overwrites the live cache with 20 names).
- Angel client: one shared rate limiter (≤ 1 historical request / 4 s, quotes 1 / s), stop on the first
  "exceeding access rate", back off for the rest of the day, show it on Health.
- Telegram / portal alert when: login fails, WebSocket down > 2 min in market hours, daily bars fail, scan fails.

## C7. News history for the event study (V8-P3)

GDELT DOC 2.0 API (free) for 2020+ headlines on the Nifty 100 names and macro terms (RBI, repo rate, Fed, war,
crude, budget), cached in `data/news/` by day; run on the Mac, not the server hot path; polite rate (1 request / 5 s).
Link each headline to the first Indian session it could affect (V8 §2.3 rule), then the CAR study in
`lab/event_study.py`. Pre-register the E* hypotheses in `docs/PREREG.md` before looking at results.

---

## Paste into Cursor (one chat per group)

```
Read AGENTS.md, docs/CURSOR_NEXT.md and (for V9) docs/PLAN_V9_OPTIONS.md. Do group <C11|C13|C6|...|V9> only, on the
branch named in the table. Every change gets a test that fails before and passes after; ruff check . and pytest -q
green; no network in tests; no secrets anywhere; never change mode or live_orders; never deploy; never push main.
End with a phase note in docs/phase-reports/<group>.md (what was built, tests, acceptance numbers, open questions).
If anything in the plan is unclear or looks wrong, stop and ask the owner, then record the answer in docs/DECISIONS.md.
```
