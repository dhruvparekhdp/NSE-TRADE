# V-FIX-2 F1 — daily bars + paper job pipeline

Branch: `feat/v-fix-2` (from `feat/v-fix-1`)  
**Not merged to `main`.**

## F1a — `job_daily_bars` (16:10 IST)

- `data/angel_daily.py`: ONE_DAY `getCandleData` (NSE), ≥0.4 s between symbols, AB1021 exponential backoff.
- First sync backfills up to **320** sessions per symbol; unadjusted Angel closes; **>35%** day-over-day → `events` row `corp_action_suspect`.
- Runner cron `10 16 * * mon-fri`; requires injected `_daily_candle_api` (SmartConnect session in prod).

## F1b — paper jobs

- `engine/paper_jobs.py`: `job_scan` (16:20), `job_pending` (09:00 count), `job_eod_fill` (16:15), `job_outcomes` (16:30).
- Lake-backed daily bars; enabled Book B strategies, or **all Book B in shadow** when `strategies_enabled` empty.
- F1/F2 filters → skip reasons `market_filter_f1_vol` / `market_filter_f2_trend` (logged on picks; F1 only when ≥273 Nifty sessions).
- Persists `signals`, `pending_orders`, `trades`, `paper_cycles` wallet, outcome `events`.

## F1c — sector cap

- `max_open_per_sector=2`, `data/sectors.py`, skip reason `sector_cap` (+ portal copy).

## F1d — dry run

```bash
python -m scripts.paper_dry_run --date 2026-01-05 --no-write --symbols X
```

## Tests

```text
pytest -q   # 271 passed (feat/v-fix-2)
ruff check .
```

## Acceptance notes

- `tests/test_f1b_paper_jobs.py`: 30 fixture days → signals/pending/trades **> 0**; DB fills match `replay_through_jobs` ⊆ `lab/backtest` (extra calendar day fill for last pending).
- Production: wire Angel `_daily_candle_api` on runner after login job; populate `instruments` tokens.

## Open

- Full DB trade list parity on last scan day without extra manual eod (scheduler always has next trading day).
- `holidays_2024.json` etc. for calendar gaps outside 2026.
