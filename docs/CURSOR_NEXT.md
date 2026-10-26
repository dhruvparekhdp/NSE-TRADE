# CURSOR NEXT: the full work queue after V8 (written by Claude, 25 Oct 2026)

Read `AGENTS.md` first, every time. Paper only: nothing here may send an order, and `mode` / `live_orders` are never
touched. One branch per ticket group, one PR each; Claude reviews every branch and does every server deploy. Never
deploy, never push `main`. Tests never touch the network; recorded fixtures have tokens stripped.

Do the groups in this order. Inside a group, tickets can go in any order.

| # | Group | Branch | Why now |
|---|---|---|---|
| C0 | Merge the deployed login + portal into v8 | `feat/v8-complete` | v8 still has the stub login and deletes the portal hubs; it cannot be deployed until this is fixed |
| C1 | Watchlist live quotes from Angel | `feat/c1-quotes` | Watchlist shows 100 symbols but stale Yahoo quotes for 20 |
| C2 | Global cues source | `feat/c2-cues` | Yahoo returns 429 from the server; Market mood has no data |
| C3 | Event calendar + date bug | `feat/c3-events` | `config/policy_dates.json` has 2025 RBI dates labelled 2026 |
| C4 | Import Claude's Angel history into the lake | `feat/c4-history` | 2019+ daily and 2020+ 1-min bars are being downloaded now |
| C5 | Lab diagnostics (signal "why" and movement) | `feat/c5-diagnostics` | Evidence page needs per-signal why / MFE / MAE / R at horizons |
| V9 | Options on news + delta-hedged vol book | `feat/v9-options` | Owner's BTST/STBT trade and delta hedging; see `docs/PLAN_V9_OPTIONS.md` |
| C6 | Live Angel WebSocket into `MultiBarFeed` | `feat/v8-live-1s` | V6-1 / V8-P2, still open in your V8 report |
| C7 | News history (GDELT) for the event study | `feat/v8-event-study` | V8-P3 needs headlines back to 2020 |
| C8 | Strategy rework after the backtests | `feat/c8-rework` | no strategy passes; new pre-registered trials |
| C9 | Secure key entry (HTTPS / CLI) | `feat/c9-keys` | the Keys page cannot save over plain HTTP (403, by design); 26 Oct MPIN change needed SSH |

## Status on Monday 26 Oct 2026 (Claude, read-only check of the server at 01:30 IST)

Safe and running: `mode=paper`, `live_orders=false`, service up (49 MB), 100 instruments, real Angel login job at
08:45, 26 Oct is a trading day, crypto-engine untouched. The 16:10 `job_daily_bars` backfills 320 sessions on its
first run (the lake holds only 5 probe files today), so the 16:20 scan has history from Monday on.

What will NOT happen today, and the ticket that fixes it:
| Gap | Effect today | Ticket |
|---|---|---|
| `strategies_enabled = []` | the scan logs shadow picks only; no paper trades open | owner decision (C8) |
| Global cues use Yahoo (429 from the server) | Market mood empty | C2 |
| Watchlist quotes use Yahoo | stale quotes for 20 names | C1 |
| No live WebSocket feed | Book A shadow job only logs a line | C6 |
| `policy_dates.json` has 2025 dates | RBI event flags wrong | C3 |
| v8 branch has stub login and no hubs | v8 cannot be deployed | C0 |

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

## C0. Merge `feat/v-fix-2-login` (e59c72c, LIVE on the server) into `feat/v8-complete`

The server runs e59c72c. `feat/v8-complete` was cut before it, so a merge is needed before v8 can ever be deployed.
- Keep from e59c72c, unchanged: `engine/angel_session.py`; in `engine/runner.py` the real `job_refresh_instruments`
  (08:30 + startup when the universe is empty), `_ensure_login`, `job_login` (08:45, retries 08:50/08:55), and
  `job_daily_bars` logging in on demand; `config/ind_nifty100list.csv`; `web/portal/hubs/{command,book,evidence,
  system}.js`; `web/portal/nav.js` with the Watchlist tab; `tests/test_angel_session.py`.
- v8 currently DELETES the four hub files and stubs `job_login` / `job_refresh_instruments` (log line only). Both are
  regressions; resolve every conflict in favour of e59c72c for those, and keep v8's additions (1 s rollup, news jobs,
  event study, market filters) around them.
- TOTP stays `pyotp.TOTP(secret).at(datetime.now(timezone.utc))`; never set `TZ` inside the process.
- Acceptance: `pytest -q` and `ruff check .` green; `git diff e59c72c -- engine/angel_session.py web/portal/hubs`
  shows only additions; portal pages Today / Market mood / Watchlist / Paper book / Signals / Evidence / Health /
  Settings all load in `tests/test_portal_shell.py`; phase note in `docs/phase-reports/V8-COMPLETE.md`.

## C1. Watchlist live quotes from Angel (replace Yahoo on this path)

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

## C4. Import Claude's Angel history into the lake

Claude is downloading (read-only, 25-26 Oct) into gzip JSON-lines files, copied to `var/angel_hist/` on the Mac:
`hist_daily.jsonl.gz` (ONE_DAY 2019-01 -> 2026-10-23, Nifty 100 + NIFTY 50 / NIFTY BANK / INDIA VIX),
`hist_idx1m.jsonl.gz` (ONE_MINUTE 2020-01 -> 2026-03 for the three indices), `hist_1m_fy<YYYY>.jsonl.gz` (Nifty 100
ONE_MINUTE per financial year), `angel_fy.jsonl.gz` (FY 2026-27 to 23 Oct, daily + 1-min).
Each line: `{"sym", "tf": "1d"|"1m", "from"?, "rows": [[iso_ts, o, h, l, c, v], ...]}` or `{"sym", "err": ...}`.
- `scripts/import_angel_jsonl.py`: stream each file (never load a whole file), dedupe on (symbol, ts), write the
  lake's existing parquet layout with `source="angel"`, UTC epoch ms. Report per symbol: first / last bar, missing
  sessions vs the NSE holiday calendar, error lines.
- Survivorship: the list is TODAY's Nifty 100. Join `config/universe_history.csv` so backtests before a stock joined
  the index can exclude it; say so in every report.
- Tests on a 3-line fixture file, including a truncated last line.

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

## C6. Live Angel WebSocket into `MultiBarFeed` (your V8 report, "still open")

SmartWebSocketV2 mode 3 for the Nifty 100 + NIFTY 50, feeding `BarBuilder1s` and 1-min bars, Book A shadow on the
live feed, reconnect with backoff, heartbeat on Health. RSS under 600 MB with 101 symbols for a full session (add a
soak test that replays a recorded hour at 60x and asserts memory).

## C7. News history for the event study (V8-P3)

GDELT DOC 2.0 API (free) for 2020+ headlines on the Nifty 100 names and macro terms (RBI, repo rate, Fed, war,
crude, budget), cached in `data/news/` by day; run on the Mac, not the server hot path; polite rate (1 request / 5 s).
Link each headline to the first Indian session it could affect (V8 §2.3 rule), then the CAR study in
`lab/event_study.py`. Pre-register the E* hypotheses in `docs/PREREG.md` before looking at results.

---

## Paste into Cursor (one chat per group)

```
Read AGENTS.md, docs/CURSOR_NEXT.md and (for V9) docs/PLAN_V9_OPTIONS.md. Do group <C0|C1|...|V9> only, on the
branch named in the table. Every change gets a test that fails before and passes after; ruff check . and pytest -q
green; no network in tests; no secrets anywhere; never change mode or live_orders; never deploy; never push main.
End with a phase note in docs/phase-reports/<group>.md (what was built, tests, acceptance numbers, open questions).
If anything in the plan is unclear or looks wrong, stop and ask the owner, then record the answer in docs/DECISIONS.md.
```
