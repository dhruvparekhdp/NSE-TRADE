# V-NEXT phase report (N1–N6)

Branch: `feat/v-next` · **Not merged to `main`.**

## What was built

| Ticket | Deliverable |
|---|---|
| N1 | `data/lake_build.py`, `scripts/build_lake.py`, `config/corp_actions.csv` scaffold, `var/reports/data_health.md` |
| N2 | `lab/trial_metrics.py`, `scripts/run_prereg_trials.py`, gate table in `docs/phase-reports/V3.md` |
| N3 | `docs/PREREG.md` T6, `S6_swing_open`, registry wiring |
| N4 | Sector cap (`max_open_per_sector=2`), `data/sectors.py`, web copy |
| N5 | `scripts/opening_study.py`, `docs/research/OPENING.md` |
| N6 | `docs/DEPLOY_PROPOSAL.md` |

## Acceptance (honest)

- **Tests:** 273 passed, `ruff check .` clean.
- **Lake:** Partial bhav backfill only — see V3.md. PREREG **no passes**; T5 **n=0** on this lake.
- **Opening study:** Descriptive on available daily data (468 Nifty-proxy sessions in latest run); not a traded edge claim.

## Open questions

1. Bhav legacy URL failures before ~2020 — alternate source or paid vendor?
2. When to merge `feat/v-fix-2` paper pipeline (F1) with this branch?
3. Owner priority: finish historical lake vs start **V8** news/event work (see research plan).

## Next

Owner-directed: complete bhav → full PREREG re-run; or branch `feat/v8-news-events` per `docs/research/NEWS_EVENT_RESEARCH.md`.
