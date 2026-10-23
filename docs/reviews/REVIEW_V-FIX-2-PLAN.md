# V-FIX-2 plan (Claude planner, after V-FIX-1 — 23 Oct 2026)

**Prerequisite:** merge `feat/v-fix-1` (review R3–R15) after Claude PR review. Do not deploy until V-FIX-2 closes the gaps below.

V-FIX-1 fixed the review’s code findings but left **engine jobs that log without lake data**, **production WebSocket**, and **owner-only research steps**. This document is the next Cursor fix round + owner checklist (mirrors `REVIEW_V0-V6.md` §5).

## 1. What V-FIX-1 left partial

| id | Area | Gap |
|---|---|---|
| F1 | `engine/runner.py` | `job_scan` / `job_eod_fill` / `job_outcomes` / `job_bhav_check` do not read daily bars from `data/lake` or persist `signals` / `trades` / `pending_orders` |
| F2 | `engine/jobs.py` | Opening scorecard job is a stub; no quotes → `opening_summary` during 09:15–09:45 |
| F3 | `engine/paper_engine.py` | Split `engine/outcomes.py` (V4-4); portal take/skip scoreboard reads one module |
| F4 | `strategies/xsmom_rank.py` | Monthly rebalance job sets `xsmom_pick` / `xsmom_exit` on `Context` for all symbols in `universe_on(date)` |
| F5 | `data/stream.py` + runner | SmartAPI WS V2 thread → `StreamHub` queue; `job_book_a_shadow` calls `shadow_scan` on 1m bars (fixture parity test) |
| F6 | `data/bars.py` | F&O last bar 15:14 when CAS regime active; wire late-tick rule (V6-2 remainder) |
| F7 | `engine/parity.py` | `job_bhav_check` compares paper trades vs bhav replay; writes `parity` events |

## 2. Owner steps (not Cursor — from REVIEW §3 + SUMMARY)

1. Bhav backfill: `python -m scripts.download_bhav --from 2012-01-01 --to <today>` on a machine with network (not CI).
2. Run `python -m scripts.run_prereg_trials` after lake exists; paste gate table into `docs/phase-reports/V3.md`.
3. Contract note → update `config/costs_angel.json` `verified_against_contract_note`.
4. Add `config/holidays_2027.json` before Jan 2027.
5. Set `gift_nifty_source` when source chosen.
6. Server: `TRUSTED_PROXY=true`, nginx headers per `docs/SERVER_SETUP.md` before exposing `/keys`.
7. Phone check portal at 375px; Angel AB1050 / TOTP when support clears.

## 3. Prompt for Cursor (V-FIX-2)

```
git fetch && git checkout main && git pull && git checkout -b feat/v-fix-2 && git merge --no-edit origin/feat/v-fix-1
(that assumes V-FIX-1 merged; if not, branch from feat/v-fix-1). Read AGENTS.md, docs/PLAN_V2.md V4–V6 timelines,
docs/phase-reports/V-FIX-1.md, and this file. Fix in order, test first, one commit per F#, ruff + pytest green,
update PROGRESS.md honestly. Never push or merge main. No network in tests; lake via fixtures under tests/fixtures/lake/.

F1  Paper jobs end-to-end: job_scan loads daily bars per symbol from Lake (fixture lake in tests); writes signals
    (pick/mirror/random) and pending_orders for next session; job_eod_fill fills and writes trades; job_outcomes
    resolves virtual_status; acceptance: extend test_r1 30-day fixture to assert DB row counts > 0 for signals/trades.
F2  Opening scorecard: job_opening_scorecard reads preopen final + first 1m open from quotes cache; upserts
    opening_summary for NIFTY + tracked symbols; test with fixture preopen + quotes.
F3  engine/outcomes.py extracted from paper_engine; imports updated; tests unchanged green.
F4  job_xsmom_rebalance (1st trading day monthly 16:25): rank universe with xsmom_rank; set picks/exits in DB or
    job metadata for next scan; test rank on 3-symbol fixture.
F5  AngelStreamAdapter (fake in tests): run_ws_loop + parse tick → BarBuilder; runner starts/stops with feed jobs;
    shadow_scan once per 5m on fixture 1m file; same signal count as lab on that file.
F6  BarBuilder flush respects sessions.json CAS window for F&O; test Aug 2026 date last bar ts.
F7  bhav_check job: compare today's paper trades to replay; parity event on mismatch; test injected fault.

Then write docs/phase-reports/V-FIX-2.md and stop for review.
```

## 4. Process

- Stack: `feat/v-fix-2` from merged `main` (post V-FIX-1).
- Claude reviews PR before owner merges.
- V7 (live orders) still requires written yes — out of scope.
