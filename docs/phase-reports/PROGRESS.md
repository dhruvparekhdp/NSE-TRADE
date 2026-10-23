# Development progress (PLAN_V2)

Resume from the first unticked ticket. Update after every ticket commit.

MVP baseline branch: `feat/mvp-backtest-news` @ f884125  
PR: https://github.com/dhruvparekhdp/NSE-TRADE/pull/new/feat/mvp-backtest-news

## V0 — hygiene (`feat/v0-hygiene`)

| id | status | commit | note |
|---|---|---|---|
| V0-1 | done | ea158de | fix 2 ruff F401; MVP PR link |
| V0-2 | done | 4a22802 | web_host 127.0.0.1; Secure cookie; HTTPS keys gate |
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
| V1-3 | done | d92c60b | derive square_off / no_entry |
| V1-4 | done | d92c60b | costs_angel.json + min brokerage ₹5 |
| V1-5 | done | d92c60b | instruments is_fo + surveillance + exposure |
| V1-6 | done | d92c60b | universe_history survivorship |
| V1-7 | done | d92c60b | UDiFF bhav + corporate actions |
| V1-8 | done | d92c60b | events.py results/expiry/MPC |

## V1b — opening (`feat/v1b-opening`)

| id | status | commit | note |
|---|---|---|---|
| V1b-1 | done | 07c787e | global_cues + flows |
| V1b-2 | done | 07c787e | preopen snapshots |
| V1b-3 | done | 07c787e | headlines fetch/tag/score |
| V1b-4 | done | 07c787e | morning brief + opening type + risk-off |
| V1b-5 | done | 07c787e | /api/opening|/sentiment|/headlines |
| V1b-6 | done | 07c787e | opening features on signals |

## V2 — lab fixes (`feat/v2-lab-fixes`)

| id | status | commit | note |
|---|---|---|---|
| V2-1 | todo | | daily fills / gap stop / trail |
| V2-2 | todo | | intraday stops both sides + targets |
| V2-3 | todo | | BarView timeframe close |
| V2-4 | todo | | real mirror/random baselines |
| V2-5 | todo | | portfolio backtest |
| V2-6 | todo | | evaluate halves + ledger columns |
| V2-7 | todo | | core/exits.py shared engine |

## V3 — research (`feat/v3-research`)

| id | status | commit | note |
|---|---|---|---|
| V3-1 | todo | | real bhavcopy lake |
| V3-2 | todo | | PREREG.md before trials |
| V3-3 | todo | | run 5 trials + gate table |

## V4 — paper (`feat/v4-paper`)

| id | status | commit | note |
|---|---|---|---|
| V4-1 | todo | | migration 002 |
| V4-2 | todo | | quotes Angel+Yahoo |
| V4-3 | todo | | PaperBroker accounting |
| V4-4 | todo | | outcomes + take/skip |
| V4-5 | todo | | Broker protocol + watchdog |
| V4-6 | todo | | paper_engine e2e parity |
| V4-7 | todo | | Telegram alerts |
| V4-8 | todo | | parity job |

## V5 — portal (`feat/v5-portal`)

| id | status | commit | note |
|---|---|---|---|
| V5-1 | todo | | crypto portal shell port |
| V5-2 | todo | | §7 endpoints + reasons |
| V5-3 | todo | | Command hub |
| V5-4 | todo | | Book hub |
| V5-5 | todo | | Evidence + System |
| V5-6 | todo | | phone 375px check |

## V6 — Book A shadow (`feat/v6-intraday-shadow`)

| id | status | commit | note |
|---|---|---|---|
| V6-1 | todo | | Angel WS |
| V6-2 | todo | | bars late-tick |
| V6-3 | todo | | Book A shadow signals |
| V6-4 | todo | | 1m history depth report |

## V7 — live (STOP — needs owner written yes)

Not started.
