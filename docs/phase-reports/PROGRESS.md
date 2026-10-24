# Development progress (PLAN_V2)

Resume from the first unticked ticket. Update after every ticket commit.

MVP baseline branch: `feat/mvp-backtest-news` @ f884125  
PR: https://github.com/dhruvparekhdp/NSE-TRADE/pull/new/feat/mvp-backtest-news

## V0 — hygiene (`feat/v0-hygiene`)

| id | status | commit | note |
|---|---|---|---|
| V0-1 | done | ea158de | fix 2 ruff F401; MVP PR link |
| V0-2 | done | e122bf7 | HTTPS keys gate + trusted_proxy (R3); nginx docs |
| V0-3 | done | 123b840 | `x if x is not None else now()` |
| V0-4 | done | 6b282b2 | core/ticks.py + tick_bands.json |
| V0-5 | done | c25b0d3 | scripts use settings.data_dir |
| V0-6 | done | 31a5227 | Test Angel read-only button + API |
| V0-7 | done | 31a5227 | smartapi-python 1.5.5 + real IP/MAC headers |
| V0-8 | done | ab5f708 | keys mask / compare / reveal / history |

## V1 — market (`feat/v1-market`)

| id | status | commit | note |
|---|---|---|---|
| V1-1 | done | c5c6fc4 | sessions.json + session_state(stock_class) |
| V1-2 | done | d92c60b | holidays / CalendarMissing / Muhurat / runner skip |
| V1-3 | done | 211ffb3 | runner crons use derive_engine_times (R9) |
| V1-4 | done | d92c60b | costs_angel.json + min brokerage ₹5 |
| V1-5 | done | d92c60b | instruments is_fo + surveillance + exposure |
| V1-6 | done | d92c60b | universe_history survivorship |
| V1-7 | done | d92c60b | UDiFF bhav + corporate actions |
| V1-8 | done | d92c60b | events.py results/expiry/MPC |

## V1b — opening (`feat/v1b-opening`)

| id | status | commit | note |
|---|---|---|---|
| V1b-1 | done | 07224e3 | global_cues + flows |
| V1b-2 | done | ded258a | preopen parse + refresh_preopen + runner job (R1) |
| V1b-3 | done | 07224e3 | headlines fetch/tag/score |
| V1b-4 | done | ded258a | morning brief job writes table; opening type job (R1) |
| V1b-5 | done | 07224e3 | /api/opening|/sentiment|/headlines |
| V1b-6 | done | 07224e3 | opening features on signals |

## V2 — lab fixes (`feat/v2-lab-fixes`)

| id | status | commit | note |
|---|---|---|---|
| V2-1 | done | dd4c9ba | daily fills / gap stop; trail ATR14 from bars (R13) |
| V2-2 | partial | ef6d956 | intraday stops; context builder + resample (R6); live runner still thin |
| V2-3 | done | c4ecc8b | daily close from sessions.json; exclude forming bars (R12) |
| V2-4 | done | 68a47f9 | baselines simulated in research scripts; gate fails if empty (R4) |
| V2-5 | done | e5e8421 | portfolio backtest |
| V2-6 | done | e5e8421 | evaluate halves + ledger columns |
| V2-7 | done | e5e8421 | core/exits.py shared engine |

## V3 — research (`feat/v3-research`)

| id | status | commit | note |
|---|---|---|---|
| V3-1 | done | 9ccff3f | bhav downloader
| V3-2 | done | 9ccff3f | PREREG.md
| V3-3 | done | 9ccff3f | trial runner + gate table

## V4 — paper (`feat/v4-paper`)

| id | status | commit | note |
|---|---|---|---|
| V4-1 | done | 87f27ea | migration 002 |
| V4-2 | done | 87f27ea | quotes Angel+Yahoo |
| V4-3 | done | 87f27ea | PaperBroker accounting |
| V4-4 | done | 87f27ea | outcomes + take/skip |
| V4-5 | partial | 5a1a6b1 | Broker protocol, crossed_since watchdog, square_off LIMIT (R8); Angel live send still gated |
| V4-6 | partial | ded258a | replay_through_jobs parity test; runner jobs log-only without lake |
| V4-7 | done | 87f27ea | Telegram alerts |
| V4-8 | done | 87f27ea | parity job |

## V5 — portal (`feat/v5-portal`)

| id | status | commit | note |
|---|---|---|---|
| V5-1 | done | 62080bd | crypto portal shell port |
| V5-2 | done | 62080bd | §7 endpoints + reasons |
| V5-3 | done | 62080bd | Command hub |
| V5-4 | done | 62080bd | Book hub |
| V5-5 | done | 62080bd | Evidence + System |
| V5-6 | done | 62080bd | phone 375px check |

## V6 — Book A shadow (`feat/v6-intraday-shadow`)

| id | status | commit | note |
|---|---|---|---|
| V6-1 | partial | 4c7d570 | reconnect loop + fakes (R15); SmartAPI WS not in runner |
| V6-2 | partial | db7a6e7 | bars late-tick helpers; F&O 15:14 rule not fully wired in runner |
| V6-3 | partial | ded258a | shadow_scan scheduled; needs live bars from WS |
| V6-4 | done | db7a6e7 | 1m history depth report |

## V-FIX-1 — review fixes (`feat/v-fix-1`)

See `docs/phase-reports/V-FIX-1.md`. R3–R15 addressed per review §5; **266** tests green.

## V-NEXT — data + PREREG + opening (`feat/v-next`)

See `docs/phase-reports/V-NEXT.md`. Gate table: `docs/phase-reports/V3.md`.

| id | status | note |
|---|---|---|
| N1 | partial | bhav resumable; lake rebuild as files land |
| N2–N6 | done | see V-NEXT.md |

## V-FIX-2 F1 — lake + paper jobs (merged into `feat/v8-complete`)

| id | status | note |
|---|---|---|
| F1a–F1d | done | daily bars, paper_jobs, sector cap, dry_run — `docs/phase-reports/V-FIX-2-F1.md` |

## V8 — news / events / FY microdata (`feat/v8-complete`)

| id | status | note |
|---|---|---|
| V8-P0 | done | Hermes-style news extract |
| V8-P1 | partial | `fy_history_depth.py` (daily; 1m backfill still manual) |
| V8-P2 | done | 1s + 1m `MultiBarFeed`, tick_smoke |
| V8-P3 | done | event_study + run_strategy_tests |
| V8-P4 | todo | PREREG E* after event base rates |

Report: `docs/phase-reports/V8-COMPLETE.md`. **289** tests green.

**Spec:** `docs/research/NEWS_EVENT_RESEARCH.md`.

## V7 — live (STOP — needs owner written yes)

Not started.
