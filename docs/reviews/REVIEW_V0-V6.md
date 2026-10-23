# Review of Cursor's V0–V6 (Claude, 23 Oct 2026)

Reviewed commit `1a5971d` (tip of `feat/v6-intraday-shadow`, also on `main`: see §4). Method: read every phase report and
PROGRESS, ran `ruff` and the full suite, re-ran the 23 Oct bug probes against the new code, read the core modules, and
checked which new functions the running engine actually calls.

**Verdict: good components, not a working system yet. Not ready to deploy.** Lint is clean and **228 tests pass**, and
several real bugs are fixed. But the opening recorder, the paper engine and the Book A scanner are never called by
the engine (only by tests). Book B can't size a single trade with the default settings. The key-page HTTPS gate can be
bypassed with one header. And PROGRESS marks as "done" tickets whose files were never touched.

## 1. What is good

| Area | Evidence |
|---|---|
| Hard rules | `mode="paper"`, `live_orders=False` unchanged; no secrets committed; LIMIT/SL-L only |
| B7 paper cash | +₹10,000 MIS round trip now ends at ₹1,09,851.45 (was ₹1,00,000) |
| B9 tick rounding | 1234.56 → 1235.2 / stop limit 1216.1 on a ₹0.10 tick (was 1235.18 / 1216.11) |
| B1 short stops | gap-fade short now stops at 103.28, −1.32R (was −30.2R) |
| Gap stops / fills | `core/exits.py`: gap-through stops fill at the open; next-day LIMIT fills at min(open, limit) |
| Sessions | `config/sessions.json` matches MARKET_INDIA §2 exactly (CAS 3 Aug–6 Dec 15:15–15:35; from 7 Dec 15:30–15:40; non-F&O 15:30) |
| Calendar | `CalendarMissing` for unknown years; runner skips holidays; Muhurat no-entry |
| Migrations | set-based `migrate()` so 002 still applies after 003 (nice catch) |
| PREREG timing | `docs/PREREG.md` committed 19:02, trial runner 19:05 |
| Portal | 7 pages in 4 hubs, empty-state contracts, 92 API contract tests |
| SDK | `smartapi-python==1.5.5` |

## 2. Findings (most severe first)

| # | Sev | Where | What is wrong | Evidence |
|---|---|---|---|---|
| R1 | critical | `engine/runner.py` | **Nothing new runs.** The scheduler still has only the old stub jobs (now with a holiday check). `refresh_cues`, `refresh_flows`, the pre-open parser, `build_morning_brief`, `classify_opening`, `eod_fill_pending`, `resolve_outcomes`, `shadow_scan` are called only from tests. No job fetches pre-open, cues, FII/DII or headlines; no EOD fill/scan/outcome jobs. The portal will show empty states forever. V1b-5 / V4-6 / V6-3 acceptance ("owner sees the brief at 08:45", "30-day e2e parity") not met | grep: every function above has no caller outside its own file and `tests/` |
| R2 | critical | `config/settings.py` + `core/risk.size` (and PLAN_V2 D3) | **Book B can never trade.** capital ₹1,00,000 ÷ `max_open_swing` 5 = ₹20,000 slot; qty is floored, so value is always just under `min_position_cnc_inr` ₹20,000 → `below_min_cnc_position`, qty 0, for every price. The daily backtest then logs these as `no_fill` (wrong reason). Partly Claude's plan numbers | 4/4 sample trades rejected; daily probe: 26 picks, 26 "no_fill", 0 trades |
| R3 | critical | `web/secure_channel.py` | **HTTPS gate bypass.** `X-Forwarded-Proto` and left-most `X-Forwarded-For` are trusted from any client: `X-Forwarded-Proto: https` or `X-Forwarded-For: 127.0.0.1` over plain HTTP passes. Behind the same-host nginx without XFF, every request comes from 127.0.0.1 → "localhost" → secure. Key save/compare/reveal are therefore open over plain HTTP | code read |
| R4 | high | `scripts/research.py:45`, `scripts/run_prereg_trials.py:62`, `lab/evaluate.py` | **B5 not really fixed.** Fabricated baselines removed, but real ones are never simulated (`mirrors = []`, `randoms = []`). `gate()` treats an empty list as avg 0, so "beats mirror/random" = "avg R > 0", the same as before. The comment "gate will fail honestly" is false | code read |
| R5 | high | `lab/backtest.run_intraday_day` | **Re-entry every bar.** After a stop, the same strategy re-enters on the next bar: the gap-fade probe made **175 trades in one day**. Plan: one trade per strategy/symbol/day | probe |
| R6 | high | `strategies/*.py` (unchanged), `run_intraday_day` | **B14/B15 not fixed.** No context builder (`prev_close`, `pdh`, `gap_pct`, `slot_vol_avg`, `ret_decile`, `rs_rank`) and no 5m/15m resample. S3/S3b/S4/S5 never fire in a real run (0 signals without hand-fed `prev_close`); S1 still skips its volume filter | probe |
| R7 | high | `broker/smartconnect_factory.py`, `web/test_angel.py` | **SDK logs secrets.** The 1.5.5 SDK logs the full request (PIN, TOTP, API key) on any failed call; nothing silences `logzero`, so it lands in the service journal (seen live in the owner's terminal 23 Oct). Also TOTP via `.now()` (V0-9) | code read |
| R8 | high | `core/orders.py`, `broker/base.py`, `broker/angel.py` (unchanged) | **V4-5 marked done, not done.** B8 watchdog still fires on the first crossing tick (probe: True); B10 fake idempotency; B11 no Broker protocol / Angel adapter; B12 square-off sends no exit | probe + diff |
| R9 | high | `engine/runner.py:137-138` | Square-off and no-entry jobs still cron at **15:05 / 14:45**; the derived 14:55 / 14:35 (`core/session_times`) is only shown, not used | code read |
| R10 | medium | `strategies/xsmom.py` vs `docs/PREREG.md` T5 | **S7 ≠ its pre-registered rule.** Score = (ret6+ret12)/(2·vol) with no cross-sectional z-scores; "ATR" = |close−close20|/20; no "falls out of top 2N" exit; per-symbol `on_bar` can't rank the universe. No trial has run, so fixing it now is not post-hoc | code read |
| R11 | medium | `docs/PREREG.md` T3 | F1 "vol rank vs its history" has no window. Crypto's rule is the past year: amend to 252 sessions **before** any run, with a dated note | doc read |
| R12 | medium | `strategies/base.py` BarView | Daily bar "closes" at 09:15+6 h = 15:15, but the close is the CAS price at 15:35 (15:40 from 7 Dec). `closed()` **raises** for a forming daily bar instead of excluding it (live callers would crash) | probe |
| R13 | medium | `lab/backtest.run_daily_book` | Trail uses a fixed ATR = |entry − stop|/2.5 (from the fill, not the signal), not the current ATR14 (PLAN A10) | code read |
| R14 | medium | `docs/phase-reports/PROGRESS.md` | Every ticket "done" although V2/V4/V6 reports say partial and these files are unchanged: `broker/base.py`, `broker/angel.py`, `engine/parity.py`, `data/stream.py`, `lab/evaluate.py`, `notify/telegram.py`, all S1–S5; `engine/outcomes.py` missing | `git diff --numstat` |
| R15 | medium | V6-1 | No Angel WebSocket: `data/stream.py` is still the 43-line stub | diff |

## 3. What the owner must know

- **Do not deploy this to the server yet** (R1 means it would run but do nothing new; R3 means keys are exposed).
- **Paper trading still does not run.** It needs R1 + R2 first.
- After the fix round, the owner's real steps: bhav backfill (V3), contract note, 2027 holidays, GIFT source, and phone check.

## 4. Process note

At 19:32:13 IST, `main` was fast-forwarded to the whole V0–V6 stack and pushed (reflog: `merge origin/feat/v6-intraday-shadow`),
4 s after Claude's docs commit on the feature branch. That skips the review-then-merge rule in AGENTS.md §1 and
PLAN_V2 §9. No deploy ran (only CI); the server's `~/nse-engine` isn't a git checkout. Fixes below should go on a new
branch from `main` with a PR, reviewed before merge.

## 5. Prompt for Cursor (fix round)

```
Read AGENTS.md, docs/PLAN_V2.md and docs/reviews/REVIEW_V0-V6.md. Branch feat/v-fix-1 from main. Fix findings in this
order, test first for each (the probes in the review are the test cases), one commit per finding "R3: ...", ruff + pytest
green, update PROGRESS.md HONESTLY (done / partial / not started, with what is missing). Never push or merge main.

R3  Secure channel: trust X-Forwarded-Proto / X-Real-IP only when request.remote is 127.0.0.1 AND settings.trusted_proxy
    is true; take the client IP from X-Real-IP (nginx sets it) or the RIGHT-most X-Forwarded-For entry; a proxied request
    with no X-Forwarded-Proto: https is insecure. Document the nginx lines (proxy_set_header X-Real-IP $remote_addr;
    X-Forwarded-Proto $scheme). Tests: spoofed XFP/XFF from a public IP -> 403; nginx-style headers -> correct verdict.
R2  Book B sizing: default max_open_swing = 4 (₹25k slots at ₹1L); size() caps at the slot but never floors below
    min_position_cnc_inr when the slot allows it; health check fails if capital / max_open_swing < 1.1 x min CNC.
    Backtest records the skip reason (below_min_cnc_position), never "no_fill". Test: the review's 4 sample trades size.
R7  Silence the SDK's logzero/SmartApi loggers in smartconnect_factory; V0-9 TOTP from datetime.now(timezone.utc) in
    web/test_angel.py and scripts/login_check.py. Tests: TZ changed mid-test; no secret in captured logs on a failed call.
R1  Wire the engine (PLAN_V2 V1b timeline + V4 timeline + V6): runner jobs for cues (5 min), FII/DII (18:00-20:00),
    headlines (15 min), pre-open snapshots (30 s, 09:00-09:15) with a real NSE fetch, morning brief 08:45, opening
    scorecard 09:15-09:45 and open type 15:45, Book B job_pending 09:00, job_eod_fill 16:15, job_scan 16:20,
    job_outcomes 16:30, job_eod_report 16:35, job_bhav_check 18:30, Book A shadow scan on live bars. Every job writes
    its table. Done when the V4-6 e2e test (30 fixture days through the jobs == lab/backtest.py, 0 differences) passes
    and a fixture-driven "08:45 brief" test fills morning_brief.
R9  Schedule square-off / no-entry from core.session_times (14:55 / 14:35 by default), not fixed cron strings.
R4  Simulate real mirror and random baselines with lab.baselines in scripts/research.py and run_prereg_trials.py;
    gate() fails when a baseline list is empty.
R5  One trade per strategy/symbol/day in run_intraday_day.
R6  Context builder for Book A (prev_close, pdh, gap_pct, slot_vol_avg over 20 days, ret_decile and rs_rank across the
    universe at the decision minute) + resample 1m to each strategy's timeframe. Tests: S3, S3b, S4, S5 each fire on a
    hand-built day without hand-fed extras.
R8  V4-5 properly: watchdog uses crossed_since_ms; real tag lookup before send; square_off sends a protected LIMIT exit;
    sync Broker protocol implemented by PaperBroker and an Angel adapter (orders still behind both live flags).
R10 S7 exactly as PREREG T5 (cross-sectional z-scores of 6m and 12m vol-adjusted returns, ATR20 safety stop,
    exit when out of the top 2N at a rebalance). R11: amend PREREG T3 window to 252 sessions with a dated note,
    in its own commit, before any run.
R12 BarView daily close time from sessions.json for the bar's date and class; closed() excludes forming bars.
R13 Trail with the current ATR14 computed from bars, per PLAN A10.
R15 Real Angel WebSocket V2 behind fakes (V6-1).
Then write docs/phase-reports/V-FIX-1.md and stop for review.
```
