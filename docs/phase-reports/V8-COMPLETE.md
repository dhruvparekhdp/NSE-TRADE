# V8 three-part delivery (`feat/v8-complete`)

## Part 1 — 1s tick + basics

- `BarBuilder1s`, `second_floor_ms`, shared bucket logic in `data/bars.py`
- `MultiBarFeed` (1s + 1m) in `data/tick_pipeline.py`
- `scripts/tick_smoke.py` offline smoke
- Tests: `tests/test_tick_1s_pipeline.py` (incl. StreamHub queue)

## Part 2 — old plan → merged stack

- Merged `feat/v-fix-2` (F1 daily bars, paper_jobs, dry_run)
- `scripts/fy_history_depth.py` for FY 2026-27 watchlist daily depth
- `engine/runner.py` `job_news` fetches RSS + `events.jsonl`
- `run_prereg_trials` merges partial trial runs into `prereg_v3.json`
- `lab/market_filters.py` unifies PREREG blocks + paper skip reasons

## Part 3 — strategy / event tests

- `lab/event_study.py` CAR + rebound summaries
- `tests/test_event_study.py`
- `scripts/run_strategy_tests.py` offline smoke → `var/reports/strategy_smoke.json`

## Tests

```text
pytest -q   # 289 passed (Oct 2026)
ruff check .
python -m scripts.tick_smoke
python -m scripts.run_strategy_tests
```

## Still open

- Live Angel WS → `MultiBarFeed` in runner (V6-1 partial)
- FY **1m** Angel backfill (needs evening keys)
- Full PREREG on complete bhav lake
- V8-P4 PREREG E* strategies after real event catalog
