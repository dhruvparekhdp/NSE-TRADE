# V-FIX-1 — review R3–R15 fix round (23 Oct 2026)

Branch: `feat/v-fix-1` (from `main` + `origin/feat/review-v0-v6`)  
Source: `docs/reviews/REVIEW_V0-V6.md` §5  
Not pushed; not merged to `main`.

## Summary

Addressed Claude review findings **R3 → R2 → R7 → R1 → R9 → R4 → R5 → R6 → R8 → R10 → R11 → R12 → R13 → R15** with test-first commits (one commit per finding where possible). **266 tests** pass; `ruff check .` green.

## Commits (fix round)

| Finding | Commit | What changed |
|---|---|---|
| R3 | e122bf7, 1db5e0e | `trusted_proxy`; proxy headers only from loopback; nginx docs in `docs/SERVER_SETUP.md` |
| R2 | 911d7f0, 91c39c3 | `max_open_swing=4`; CNC sizing bump; `book_b_slot_ok` on `/api/health` |
| R7 | e0207c6 | Silence SmartAPI/logzero; `totp_now_utc` |
| R1 | ded258a | `engine/jobs.py`, runner schedule, preopen persist, 30-day job/lab parity test |
| R9 | 211ffb3 | Square-off / no-entry crons from `derive_engine_times` |
| R4 | 68a47f9 | Real baselines in research scripts; empty baseline gate failure |
| R5 | d5290e7 | One trade per strategy/symbol/day in `run_intraday_day` |
| R6 | ef6d956 | `lab/context.py`; resample before `on_bar` |
| R8 | 5a1a6b1, b640307 | Broker protocol; `crossed_since_ms` watchdog; square-off LIMIT exit |
| R10 | ad52c69 | `xsmom_rank.py`; ATR20 stop; top-2N exit hook |
| R11 | f9be430 | PREREG T3 252-session window (dated note) |
| R12 | c4ecc8b | `core/sessions.py`; daily `BarView.closed()` excludes forming bars |
| R13 | dd4c9ba | Trail uses ATR14 from daily bars |
| R15 | 4c7d570 | `run_ws_loop` + fake WS reconnect test (no live Angel WS yet) |

## Acceptance vs review

| Item | Status |
|---|---|
| R3 spoofed XFP/XFF | Tests + `TRUSTED_PROXY` gate |
| R2 four sample trades size | `tests/test_r2_book_b_sizing.py` |
| R1 30-day e2e == lab | `tests/test_r1_engine_jobs.py` (fixture strategy) |
| R1 owner sees brief 08:45 | `job_morning_brief` writes `morning_brief` table (fixture test) |
| R1 all jobs write tables | **Partial**: cues/flows/preopen/brief wired; scan/outcomes/bhav still log-only without lake + enabled strategies |
| R8 full V4-5 | Watchdog/tags/square-off improved; live Angel adapter still behind dual gate |
| R15 production WS | Reconnect loop + fakes only — SmartAPI thread not wired to runner |
| R10 S7 in live portfolio | Ranking in `xsmom_rank`; monthly portfolio job must call it (follow-up) |

## Tests

```text
pytest -q   # 266 passed (Oct 2026, feat/v-fix-1)
ruff check .
```

## Open for owner / next PR

- Deploy only after review: set `TRUSTED_PROXY=true` on nginx hosts.
- Wire `job_scan` / `job_outcomes` to lake bars and persist signals/trades when `strategies_enabled` non-empty.
- Real Angel WebSocket in runner (R15 production path).
- `engine/outcomes.py` split from `paper_engine` if desired by plan.
- Bhav backfill + PREREG trials on real lake (V3 owner steps).
