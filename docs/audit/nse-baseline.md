# NSE-TRADE baseline audit (AUD-3)

Read-only audit of `main` at `aae5f1f2674547083edd2d325db3646e7fe4876e` (merge of PR #5, 2026-10-29 13:55 IST). No broker calls were made. No `.env` values were printed. The only files this ticket adds are this audit and `docs/handoff/AUD-3.md`.

## Plan

| Area | Files read | Approach |
|---|---|---|
| Layout and rules | `README.md`, `AGENTS.md`, `docs/PLAN.md`, `docs/PLAN_V2.md`, `docs/DECISIONS.md`, phase reports | Treat `main` as the running tree. `docs/audit/` did not exist. |
| Trading surface | `broker/`, `core/orders.py`, `core/risk.py`, `engine/`, `strategies/`, `lab/`, `news/`, `data/universe.py`, `data/instruments.py` | Trace place / modify / cancel and mark runner jobs that only log. |
| HTTP | `web/app.py`, `web/auth.py`, `web/portal_api.py`, `web/keys.py`, `web/secure_channel.py`, `engine/runner.py` | Bind, cookie, auth, TLS. |
| Stores and deploy | `engine/state.py`, `storage/pg.py`, `deploy/`, `.github/workflows/`, `docs/SERVER_SETUP.md`, `docs/SHARED_INFRA.md`, `docs/RUNBOOK.md` | Compare docs with code. |
| Branches | every `origin/*` ref | Ahead/behind vs `main`, containment, merge safety. |
| Secrets | all 115 commits, 574 text blobs | Pattern scan. Report file + commit only. Never a value. |
| Tests | pinned `requirements.txt` + `requirements-dev.txt` | `ruff`, `pytest`, `compileall`. No mypy config in the repo. |

## What this tree is

NSE cash-equity research and paper engine for Angel One SmartAPI. Package name `nse-engine`. Paper is the default. Real orders need `mode=live` and `live_orders=true`, both defaulting off (`config/settings.py:42-43`). Pytest forces both off (`tests/conftest.py:10-22`, `config/settings.py:14-18` and `:124-129`).

`docs/phase-reports/SUMMARY.md` describes `feat/v6-intraday-shadow` as the tip of a stack that should not be merged. That stack is already in `main`. Later engine work lives on unmerged branches (section 9).

## 1. SmartAPI integration

| Piece | Where | On `main` |
|---|---|---|
| SDK pin | `requirements.txt` (`smartapi-python==1.5.5`, `pyotp`, `websocket-client`) | Installed by deploy. Not imported at process start. |
| Session wrapper | `broker/angel.py` `login` (`:56`) | `generateSession(client, pin, totp)`. Maps AB1021 to `RateLimited`. |
| Read methods | `profile`, `funds` (`rmsLimit`), `ltp`, `candles` (`getCandleData`, 5 retries) | No order side effect. |
| Order methods | `place_order` `:112`, `modify_order` `:120`, `cancel_order` `:128` | Call `placeOrder` / `modifyOrder` / `cancelOrder` only after `_live_guard`. |
| Header stamp | `broker/smartconnect_factory.py` | Sets public IP, local IP, MAC on a `SmartConnect` instance. `build_smart_connect` is not called by the runner. |
| Read-only login script | `scripts/login_check.py:32` | Login, profile, funds, one LTP. Does not place, modify, or cancel. |
| Portal "Test Angel" | `web/test_angel.py:32` | Login, funds, holdings, positions, logout. Admin cookie, secure-channel check, 2-minute rate limit (`:135-141`). |
| Candle backfill | `scripts/backfill.py:43-46` | `--angel` prints a message and returns. It does not call the SDK. |
| WebSocket | `data/stream.py` | In-process queue stub. `connected=True` is set locally. No Angel socket. |

Login material is `SecretStr`: `angel_api_key`, `angel_client_code`, `angel_pin`, `angel_totp_secret` (`config/settings.py:31-34`). Empty unless `.env` or Postgres supplies them (`config/secrets_loader.py`).

## 2. Nifty 100 universe

The plan says the universe is the Nifty 100. The code does not load a live Nifty 100 list.

- `data/instruments.py:12-33` `NIFTY100_SEED` is 20 symbols.
- `tests/fixtures/nse/nifty100.csv` has 10 symbols. There is no production CSV in the repo.
- `config/universe_history.csv` is a 5-name fixture (`RELIANCE`, `TCS`, `SBIN`, `OLDCO`, `NEWNIFTY`).
- `data/universe.py:23-35` `universe_on()` starts from an empty set and applies that file. It does not fall back to the 20-name seed when the file exists. Backtests that call `symbols_tradable_on` (`lab/backtest.py:17-21`) therefore see the fixture names, not the index.
- Scrip-master join (`parse_scrip_master`, `build_universe`) is implemented and tested. Nothing on the runner downloads the Angel scrip master. `job_refresh_instruments` only logs (`engine/runner.py:54-57`).
- Free quotes poll the first 20 seed names (`data/free_quotes.py:173-176`, runner `:118-126`).
- Portal exclude list is a runtime setting (`web/portal_api.py:215-236`). It does not change `universe_on()`.

## 3. MIS and CNC books

Book A is intraday MIS. Book B is delivery CNC. The mapping is consistent in the pure code and inconsistent with the scheduler.

| Book | Product | Where it is real | Where it is not |
|---|---|---|---|
| A MIS | `INTRADAY` in `core/orders.py:91`; costs in `core/costs.py` | Strategies S1–S5. `lab/backtest.py:211` `run_intraday_day`. `engine/book_a_shadow.py` virtual outcomes. `PaperBroker` margin 20% (`broker/paper.py:153`). | Runner square-off and "no new entries" jobs only log (`engine/runner.py:69-77`). Shadow scan is not scheduled. |
| B CNC | `DELIVERY` in `core/orders.py:91`; `ExitRules(product="CNC")` | S6, S6b, S7. `run_daily_book` (`lab/backtest.py:77`). `engine/paper_engine.py` virtual fills. CNC rejects shorts and checks cash (`broker/paper.py:139-151`). Min position ₹20,000 (`config/settings.py:53`, `core/risk.py:82`). | `job_eod` only logs (`engine/runner.py:84-87`). `eod_fill_pending` / `resolve_outcomes` have no runner caller. |

`strategies_enabled` defaults to empty (`config/settings.py:47`). `book_a_mode` defaults to `shadow` and the type allows `paper` (`:68`), but the portal whitelist allows only `off` and `shadow` (`web/portal_data.py:1106`). Nothing on `main` reads `book_a_mode` to send an order.

`can_open` (`core/risk.py:95`) is the shared entry gate: kill switch, surveillance, capital floor, daily loss (Book A only), session, open-slot caps, MIS exposure, one position per symbol, spread, circuit, results day, optional news filter. The backtester calls it. `OrderManager` and `AngelBroker` do not.

## 4. Strategies

Registered in `strategies/registry.py`. All nine have an `on_bar` implementation. They are pure signal functions. They do not import the broker.

| Id | Class | Book | Bar |
|---|---|---|---|
| S1_orb | `ORB` | A | 5m (implemented on the bars it is given) |
| S2_vwap | `VWAPRevert` | A | 5m |
| S3_gapfade | `GapFade` | A | 15m |
| S3b_gapgo | `GapAndGo` | A | 15m |
| S4_momo | `AfternoonMomo` | A | 5m |
| S5_pdh_rs | `PDHRS` | A | 5m |
| S6_swing | `SwingDonchian` | B | 1d |
| S6b_keltner | `SwingKeltner` | B | 1d |
| S7_xsmom | `XSMom` | B | 1d (rank is portfolio-level) |

`scripts/research.py` runs one symbol through `run_daily_book` and records a row in the SQLite ledger. It does not send orders.

## 5. Backtesting

`lab/backtest.py` is the shared fill engine (`core/exits.py` for the daily path). `run_daily_book` simulates CNC limit fills, gap stops, and a trail. `run_intraday_day` simulates one MIS day. Costs come from `core/costs.py` / `config/costs_angel.json`.

`lab/evaluate.py:39` `gate` requires avg R ≥ 0.10 on both halves, n ≥ 100 (Book B) or 200 (Book A) per half, a win against mirror and random, and a 1.5× cost stress. `lab/ledger.py` stores trials in SQLite `lab_trials` (migration `engine/migrations/004_lab_trials.sql`). `docs/PREREG.md` lists T1–T5. The phase summary says the bhav history and the gate table are not filled yet (`docs/phase-reports/SUMMARY.md`).

`lab/portfolio.py` walks `universe_on(date)`, so it inherits the fixture universe.

## 6. News and sentiment

Off by default. `news_filter_enabled=false` (`config/settings.py:109`). When on, `can_open` can block longs or shorts (`core/risk.py:132-137`). Nothing on the runner turns the filter on.

| Module | Role on `main` |
|---|---|
| `news/sentiment.py` | Keyword score in [-1, +1]. No LLM. |
| `news/india_rules.py` | Event tag from FinBERT-style probabilities. |
| `news/foreign.py` | Snapshot builder. |
| `news/scrape.py:51` `fetch_feed` | RSS fetch exists. No caller. |
| `news/pipeline.py` `refresh_and_score` | Scores the list it is given and reads an optional shared JSONL. |
| `engine/runner.py:97` `job_news` | Calls `refresh_and_score([])`. India RSS is not fetched. This job is a stub with a live function underneath. |
| `integrations/llm_client.py` | Optional Groq / OpenRouter. `ai_news_review_enabled` defaults false. |
| `integrations/hf_space.py` | Optional FinBERT HTTP classify. |

Opening and global cues (`engine/opening.py`, `data/global_cues.py`, `data/flows.py`) are record-and-display. `gift_nifty_source` defaults to `none`.

## 7. Paper and shadow

| Mode | Code | Wired into `engine.runner` on `main`? |
|---|---|---|
| Shadow Book A | `engine/book_a_shadow.py` `shadow_scan` / `shadow_outcomes`. Docstring: never places orders. | No. |
| Paper Book B | `engine/paper_engine.py` `eod_fill_pending` / `resolve_outcomes`. Virtual bars, not `PaperBroker`. | No. `job_eod` logs only. |
| In-memory broker | `broker/paper.py` | Only from tests and from `OrderManager` if a caller constructs one. The runner does not. |
| Settings default | `mode=paper`, `live_orders=false`, `book_a_mode=shadow` | Portal cannot set `mode`, `live_orders`, or `book_a_mode=paper` (`web/portal_data.py:1100-1107`). |

`engine/parity.py` compares two trade lists. The runner does not call it. The 18:30 backup job does not run the SQLite `.backup` the plan describes.

## 8. Scheduled runner

Clock is `Asia/Kolkata` (`engine/runner.py:23`, `:131-150`). Jobs skip non-sessions via `data.calendar.job_should_run`, except backup. `STUB` means the body only logs.

| Cron (IST, Mon–Fri unless noted) | Id | Status |
|---|---|---|
| 08:30 | `refresh_instruments` | STUB (`:54`) |
| 08:45 | `login` | STUB (`:59`) |
| 09:00 | `start_feed` | STUB (`:64`) |
| 14:45 | `no_new_entries` | STUB (`:69`). Also skips Muhurat when `trade_special_sessions` is false. |
| 15:05 | `square_off` | STUB (`:74`). Does not cancel or flatten. |
| 15:35 | `stop_feed` | STUB (`:79`) |
| 15:45 | `eod` | STUB (`:84`) |
| 18:00 | `backfill` | STUB (`:89`) |
| 18:30 every day | `backup` | STUB (`:94`). No SQLite backup file is written. |
| every 15 min 08–16 | `news` | Partial stub (`:97`). Scores an empty India list. Does not call `fetch_feed`. |
| every 5 min 09–15 | `free_quotes` | Live. Yahoo chart poll, first 20 seed symbols, plus one shot at boot (`:163`). |
| — | `job_free_quotes_boot` | Same function, once at start. |

Not scheduled, despite existing as functions: cues, pre-open, opening scorecard, Book A shadow, Book B scan, EOD fill, outcomes, FII/DII, bhav parity. Those are wired on unmerged branches (section 9), not on `main`.

Process entry: `python -m engine.runner`. Bind `settings.web_host:web_port` (`engine/runner.py:167`), default `127.0.0.1:8090`.

## 9. Branches compared with `main`

`main` is `aae5f1f`. Every unmerged branch is 2 commits behind that tip: `7e8703f` (cooldown `None` vs monotonic `0.0`) and the merge commit `aae5f1f`. Fork point of the unmerged engine work is `1a5971d`.

### Already contained in `main` (nothing left to merge)

`feat/mvp-backtest-news`, `feat/v0-hygiene`, `feat/v1-market`, `feat/v1b-opening`, `feat/v2-lab-fixes`, `feat/v3-research`, `feat/v4-paper`, `feat/v5-portal`, `feat/v6-intraday-shadow`, `fix/monotonic-cooldown`.

### Unmerged

Containment: `feat/review-v0-v6` ⊂ `feat/v-fix-1` ⊂ (`feat/v-fix-2` and `feat/v-next` and `feat/review-v-fix-2`). `feat/v-fix-2` ⊂ `feat/portal-hubs` ⊂ `feat/v-fix-2-login`. From there the line splits. `feat/v-next` ⊂ `feat/v8-news-p0` ⊂ `feat/v8-complete` ⊂ `feat/c17-paper-book` ⊂ `fix/runtime-overrides` ⊂ `feat/c19-monday-paper` ⊂ `fix/c19-review`. `deploy/20261026` and `feat/review-v-fix-2` and `feat/v9-plan` are not inside `fix/c19-review`.

| Branch | Adds beyond its parent | Safe to merge into `main`? |
|---|---|---|
| `feat/review-v0-v6` | 2 docs commits (V0–V6 review). | Yes, docs only. Expect a trivial merge with the 2 commits `main` has since the fork. |
| `feat/v-fix-1` | Wires runner jobs, Angel websocket loop behind fakes, order-manager signature, TOTP-from-UTC, proxy-header trust flag. | No. Superseded by `fix/c19-review`. Merging this alone drops later paper fixes. |
| `feat/review-v-fix-2` | 3 docs commits on top of `v-fix-1`. | No. Same code as `v-fix-1` plus docs that never landed on the later line. Cherry-pick the docs if wanted. |
| `feat/v-fix-2` | Book B paper scan/fill/outcomes, Angel daily bars, sector cap, dry-run CLI. | No. Ancestor of the tip. |
| `feat/portal-hubs` | Portal hub pages. | No. Ancestor of the tip. |
| `feat/v-fix-2-login` | Scheduled Angel login and Nifty instrument refresh. Read APIs, not `placeOrder`. | No. Ancestor of the tip. Do not deploy on its own. |
| `feat/v-next` | Lake build, sector cap, opening study, deploy notes, V8 news plan. Includes a "WIP, paused" commit. | No. |
| `feat/v8-news-p0` | Headline extract / event JSONL. | No. Inside the tip. |
| `deploy/20261026` | News RSS fetch, pre-open JSON shape, portal vol rank, a second copy of the cooldown fix. | No. Those three fixes were replayed onto `feat/v8-complete` with different hashes. Merging both duplicates them. |
| `feat/v8-complete` | The deploy-line fixes plus local env sync, FY backfill CLI, tick rollup. Commit `367917c` adds a loader for gitignored `config/angel.env` (template only is committed). | No. Inside the tip. The backfill CLI logs into Angel. It does not place orders. Do not run it from a review box with live flags. |
| `feat/c17-paper-book` | Paper slot, cash, idempotent jobs, market filter. | No. Inside the tip. |
| `fix/runtime-overrides` | Postgres key load no longer clears SQLite runtime settings. | No as a standalone. Worth keeping as part of the tip. It is a real bugfix `main` does not have. |
| `feat/c19-monday-paper` | Book A 1-minute paper, login lockout after repeated AB1007, health shows login/feeds. | No as a standalone. |
| `fix/c19-review` | Book A paper equity = wallet + open P&L. Tip of the engine stack (62 commits ahead). | Not as a blind merge. See below. |
| `feat/v9-plan` | Docs (V9 options, backtest notes, ticket queue) plus `scripts/stopgap/` (replay, chart backfill, `set_mpin.py`, `ws_recorder.py`). | Docs and scripts only. `set_mpin.py` reads an MPIN from the terminal and calls `save_key`. It does not contain a PIN. Do not run the stopgaps as part of merging. A merge will not update the engine. |

`fix/c19-review` vs `main`, order-relevant delta:

- `broker/angel.py` `place_order` takes the same keyword arguments as `OrderManager` and still calls `_live_guard` before `placeOrder`. New `place_order_raw` has the same guard.
- `engine/runner.py` actually logs into Angel (`job_login` → `_ensure_login`) and runs Book A paper and Book B scan/fill against SQLite and the lake. Those paper jobs do not call `AngelBroker.place_order`.
- Stubs that remain on the tip: `job_start_feed`, `job_book_a_shadow`, `job_no_new_entries`, `job_square_off`, `job_stop_feed`, `job_eod_report`, `job_bhav_check`, `job_backfill`, `job_backup`. `job_news` does fetch RSS on that branch.
- Defaults of `mode` and `live_orders` are unchanged.
- The branch is not a fast-forward. It will conflict with `7e8703f` because `deploy/20261026` and `feat/v8-complete` carry another copy of that cooldown fix.

Merge verdict: do not merge any engine branch into `main` until someone rebases `fix/c19-review` onto current `main`, re-runs the suite, and confirms the new runner jobs still cannot call `placeOrder` with the default settings. Merging is not "safe" in the sense of a no-op. It turns on scheduled Angel logins and a paper ledger. It does not, by itself, turn on live orders.

## 10. SQLite, Postgres, and the deploy docs

| Store | Code | What the docs say |
|---|---|---|
| SQLite `var/engine.db` (WAL) | `engine/state.py`. Tables: instruments, sessions, signals, orders, trades, settings, events, lab trials, opening (migrations 001–004). Portal reads this. `lab/ledger.py`, `data/flows.py`, `data/global_cues.py` use the same file. | `docs/PLAN.md` A7: SQLite only, nothing shared with crypto. Backup at 18:30. The backup job is a stub, so that backup does not happen. |
| Postgres `DATABASE_URL` | `storage/pg.py`. Tables `app_settings`, `app_settings_history`, `audit_events`, `schema_version`. Sync `psycopg` 3.2.4. Not asyncpg. | `docs/DECISIONS.md` (2026-10-23): keys live in RDS database `nse_engine` on the crypto host. `docs/SHARED_INFRA.md` says trading databases are not shared. That matches the code: Postgres holds keys and audit rows, not orders. |
| Parquet lake | `data/lake.py` | Plan and code agree. |
| Missing `DATABASE_URL` | `config/secrets_loader.py:20-21` logs and returns. The process still starts. Keys then come only from `.env`. | Bootstrap script treats `DATABASE_URL` as required (`deploy/bootstrap_server.sh:57`). |

Deploy contradictions:

- `config/settings.py:91` binds `127.0.0.1`. `deploy/nse-engine.service` does not override `WEB_HOST`. `deploy/bootstrap_server.sh:29` writes `WEB_HOST=127.0.0.1`.
- The same script writes `COOKIE_SECURE=false` (`:31`), which overrides the code default `cookie_secure=True` (`config/settings.py:93`). `docs/phase-reports/V0.md` records that as intentional until TLS.
- `docs/PLAN.md` and `docs/SERVER_SETUP.md` say Tailscale only, no public port. `docs/DECISIONS.md` and `docs/PLAN_V2.md` B24 say the portal was published with nginx on port 80 at `/nse/` over plain HTTP. There is no nginx config in the repo.
- `deploy/bootstrap_server.sh:73` prints a public `http://<ip>:8090/` URL. With `WEB_HOST=127.0.0.1` that port is not reachable from the internet. The message and the bind disagree. DECISIONS describes port 80 and path `/nse/`, not 8090.
- `.github/workflows/deploy.yml` deploys on push to `main`: `git pull --ff-only`, pip install, `systemctl restart`, curl `127.0.0.1:8090/api/health`. Market-hours block is `scripts/market_hours_guard`. `workflow_dispatch` input `force=true` bypasses it (`deploy.yml:7-10`, `:44`).
- `deploy/bootstrap_server.sh:60` prints the part of `DATABASE_URL` after `@` (host fragment, up to 40 characters) on success. `:64` installs passwordless `systemctl` for the ubuntu user.
- CI (`.github/workflows/ci.yml`) runs ruff and pytest on `main`, `feat/**`, and pull requests. It does not run a type checker. `pyproject.toml` has no mypy or pyright section.

## 11. Every place, modify, and cancel path

Searched for `place_order`, `modify_order`, `cancel_order`, `placeOrder`, `modifyOrder`, `cancelOrder`.

| Path | File:line | Effect | What stops it |
|---|---|---|---|
| `AngelBroker.place_order` | `broker/angel.py:112-118` | `api.placeOrder` | `_live_guard` (`:107-110`): both `mode=="live"` and `live_orders`. Then 5 orders/s (`orders_per_second`, `:34-40`). Default flags are off. Pytest cannot set `live_orders`. No production caller on `main`. Kill switch is not read here. |
| `AngelBroker.modify_order` | `broker/angel.py:120-126` | `api.modifyOrder` | Same guard and throttle. No caller outside the method. |
| `AngelBroker.cancel_order` | `broker/angel.py:128-134` | `api.cancelOrder` | Same guard and throttle. No caller outside the method. |
| `OrderManager.submit_bracket` | `core/orders.py:125-135` | `broker.place_order(**kwargs)` entry | No mode, live, or kill check in this class. On `main` the kwargs do not match `AngelBroker.place_order(params: dict)`, so passing the Angel object raises `TypeError` before a send. Callers on `main` are tests, which pass `PaperBroker`. |
| `OrderManager._place_exits` | `core/orders.py:197-207`, `:226-236` | stop and target | Same as above. |
| `OrderManager.tick_watchdog` | `core/orders.py:253`, `:260-270` | cancel stop, place exit | Same. |
| `OrderManager.on_fill` | `core/orders.py:173`, `:177` | cancel the other leg | Same. |
| `OrderManager.cancel_unfilled_entries` | `core/orders.py:277` | cancel entry | Same. |
| `OrderManager.square_off` | `core/orders.py:287` | cancel stop and target | Same. Does not itself place the flatten. |
| `PaperBroker.place_order` | `broker/paper.py:196-231` | In-memory order | Rejects an entry when `session_open` is false (`:197`). Idempotent on `client_tag`. No network. |
| `PaperBroker.cancel_order` | `broker/paper.py:233-238` | Marks the memory order cancelled | Only if status is open, submitted, or partial. |
| `Broker` protocol | `broker/base.py:11` | Async stub body is `...` | Not implemented. Not used as the live object. |
| `scripts/login_check.py` | `:32-46` | `generateSession`, profile, funds, LTP | No place, modify, or cancel. Prints cash. |
| `web/test_angel.py` `run_test_angel` | `:60-127` | Login and reads, then logout | No place, modify, or cancel. HTTP: admin + secure channel + 120s rate limit. |
| `scripts/backfill.py --angel` | `:43-46` | Prints and returns | No SDK call. |
| Lab, shadow, `paper_engine` | `lab/backtest.py`, `engine/book_a_shadow.py`, `engine/paper_engine.py` | Simulated fills | No broker object. |

`POST /api/kill` (`web/app.py:101-114`) stores `kill_switch` in SQLite. `can_open` honours it (`core/risk.py:105-106`). The Angel methods do not. On `main` that gap is latent, because the runner never builds an `AngelBroker` for orders. It becomes real on any branch that connects `OrderManager` to `AngelBroker` while leaving the guard only on the two flags.

Planned static-IP kill (`docs/PLAN.md`) is not implemented. `expected_static_ip` is only copied into SmartAPI headers (`broker/smartconnect_factory.py:31-35`) and shown on the guard page (`web/portal_data.py:636`).

## 12. Admin and HTTP surface

Process: aiohttp, no TLS inside the process. Default bind `127.0.0.1:8090` (`config/settings.py:91-92`, `engine/runner.py:167`). Cookie `nse_session` is HttpOnly, SameSite=Lax, 12h, `Secure` when `cookie_secure` is true (`web/app.py:89-97`, `web/auth.py:14-15`). Bootstrap sets `COOKIE_SECURE=false`.

`require_secure_channel` (`web/secure_channel.py:26-46`) treats the request as safe when `X-Forwarded-Proto` is `https`, or `request.secure`, or the client IP is loopback or `100.64.0.0/10`. `peer_ip` (`:10-15`) uses the left-most `X-Forwarded-For` with no trusted-proxy flag. A reverse proxy that appends the client header will accept a forged left-most `127.0.0.1` or a forged `https` proto. The unmerged `v-fix-1` line starts to fix that. `main` does not have the fix.

| Route | Auth on `main` | Notes |
|---|---|---|
| `GET /api/health`, `GET /api/books` | none | `web/app.py:137-138` |
| `POST /api/login` | none (this is the login) | No rate limit. `web/app.py:65`. Plaintext compare if `ADMIN_PASSWORD` is set and `PORTAL_ADMIN_HASH` is empty (`:75-78`). |
| `POST /api/kill` | admin cookie | No secure-channel check. `web/app.py:101` |
| `GET /`, `GET /nse`, SPA fallback, `/static/`, `/portal/static/` | none | HTML and assets. `web/portal_shell.py:119-125` |
| `GET /keys` | none for the HTML | The page calls the APIs, which require the cookie. `web/keys.py:209` |
| `GET /api/keys` | admin | Masked rows. `web/keys.py:216` |
| `POST /api/keys/save`, `clear`, `compare`, `reveal` | admin + secure channel | Reveal also re-checks the password and allows 5 per 10 minutes (`web/keys.py:245-272`). Returns the secret value to the caller. |
| `POST /api/keys/test-angel` | admin + secure channel | Read-only Angel. |
| `GET /api/today`, `strategies`, `quotes`, `market`, `swing`, `paper`, `signals`, `lab`, `golive`, `guard`, `data-health`, `opening`, `sentiment`, `headlines`, `events`, `universe`, `POST` is not used on these | none | `web/portal_api.py:241-257`, `:261` |
| `POST /api/quotes/refresh` | admin | Hits Yahoo. `:243` |
| `GET /api/tables`, `GET/POST /api/settings` | admin | Settings writes also need a secure channel. Whitelist cannot set `mode` or `live_orders`. |
| `POST /api/universe/exclude` | admin + secure channel | |

If the host nginx from DECISIONS is still in front of this process, unauthenticated JSON (positions, signals, lab, health) is reachable without the admin cookie. The code comment in `web/portal_api.py:5-7` says reads are open because Tailscale or the admin gate sits in front. The admin gate is not on those routes.

`web/auth.py:18-35` derives the HMAC key from `SECRETS_MASTER_KEY` or from the admin password when `SESSION_SECRET` is unset. A leaked admin password forges a session cookie.

## 13. Secrets in git

Scan: every commit (`git rev-list --all`, 115 commits), text blobs scored for assignments of key / PIN / TOTP / token / `DATABASE_URL` and for AKIA, PEM, GitHub PATs, Slack tokens, Telegram bot tokens, `sk-` keys, JWTs, and Postgres URLs that contain a password. Output of the scan was file, commit, and a class (empty, placeholder, code reference, fixture). Values were not printed and are not copied here.

No commit contains a filled `.env`, `config/angel.env`, a `.pem`, or a private key. Those filenames are absent from every tree.

| File | Commit | What is there |
|---|---|---|
| `.env.example` | `f8841256df78419fdb05c2d86a58a378a15d93d3` | Names only. Values empty. Still on `main`. |
| `config/angel.env.example` | `19473d3e0017d24a998ccee4f7449faa8a575b26`, updated `367917c26f9f1e5cc5962edf4991571f20d152a2` | Empty Angel assignments. Not on `main`. The real `config/angel.env` was never committed. |
| `deploy/bootstrap_server.sh` | `4a22802326afac2f59684c79604db5bbb83ffa1a` (on `main`) | Copies `DATABASE_URL`, `SECRETS_MASTER_KEY`, and `ADMIN_PASSWORD` from the crypto env at runtime. The secret values are not in the file. |
| `tests/test_sync_local_env.py` | `12dfd4d3efd0` and `e126b3b3a0bc` (not on `main`) | Short fixture strings. Not an RDS URL and not a TOTP seed. |
| `docs/DECISIONS.md` | `1a5971def520229d25453d5a2a5557bcfea488fe` | Narrative that a TOTP seed was pasted in chat and that the SDK printed the API key, client id, and MPIN to a terminal. The values are not in the file. The same commit records live account cash and holdings figures. Those figures are not repeated in this audit. |

`config/secret_box.py:34-36`: if `SECRETS_MASTER_KEY` is unset, `seal()` stores the API key in Postgres as plaintext. That is a code path, not a committed secret.

## 14. Tests run on this audit

Dependencies: pinned `requirements.txt` and `requirements-dev.txt` into a temp prefix. No package was upgraded. No network tests.

| Command | Result | When |
|---|---|---|
| `python3 -m ruff check .` | All checks passed (exit 0) | 2026-11-06 18:02 IST |
| `python3 -m pytest -q --tb=line` | 230 passed in 47.55s (exit 0) | same run |
| `python3 -m compileall -q` | exit 0 | same run |

`requirements-dev.txt` is pytest, pytest-asyncio, and ruff. There is no mypy or pyright configuration, so no type checker was run. CI does not run one either.

## 15. Findings, highest risk first

1. **High. Live order methods exist and ignore the kill switch.** `broker/angel.py:107-133`. Two flags default off and tests lock `live_orders` false, and `main` has no caller. `core/risk.py:105` and `POST /api/kill` do not apply to these methods. A later branch that wires `OrderManager` to `AngelBroker` (`fix/c19-review` already matches the call signature) will send real orders whenever both flags are true, including while the kill switch is on. Static-IP mismatch does not trip the kill switch.

2. **High. Plain-HTTP deployment fights the secure defaults.** `deploy/bootstrap_server.sh:31` sets `COOKIE_SECURE=false`. `web/secure_channel.py:10-41` trusts client `X-Forwarded-For` and `X-Forwarded-Proto`. `docs/DECISIONS.md` records a public nginx port 80 `/nse/` deployment. There is no nginx or TLS file in the repo. Admin session cookies and the keys page are exposed if that proxy is still the front door. `POST /api/keys/reveal` (`web/keys.py:271`) returns the stored secret to the browser.

3. **High. Most JSON reads have no auth.** `web/app.py:137-138`, `web/portal_api.py:241-257`. Health, books, positions, signals, lab, headlines, and universe are open. Safe only while the bind stays on loopback and no proxy publishes the port. The documented nginx front end removes that assumption.

4. **Medium. `OrderManager` is an unguarded order router.** `core/orders.py:125`, `:173`, `:177`, `:197`, `:226`, `:253`, `:260`, `:277`, `:287`. It does not check `mode`, `live_orders`, or `kill_switch`. On `main` the Angel signature mismatch makes a mistaken wiring fail closed. That mismatch is gone on `fix/c19-review`.

5. **Medium. Keys are stored in cleartext when the master key is missing.** `config/secret_box.py:34-36`. `save_key` will persist whatever `seal` returns (`config/secrets_loader.py:54`).

6. **Medium. Bootstrap leaks a database host fragment and installs passwordless restart.** `deploy/bootstrap_server.sh:60` and `:64`. `:73` advertises a public URL on port 8090 that the bind line does not open.

7. **Medium. The Nifty 100 universe is a fixture.** `config/universe_history.csv`, `data/universe.py:23-35`, `data/instruments.py:12-33`. Research that cites `universe_on` is not running on the index. The instrument-refresh job is a stub (`engine/runner.py:54-57`).

8. **Medium. Unmerged `fix/c19-review` is the real engine and is not safe to merge blindly.** It schedules Angel login and paper ledgers. Live flags stay off and `placeOrder` stays behind `_live_guard`, but the branch is 2 commits behind `main`, carries a duplicate cooldown fix, and removes the accidental signature mismatch in finding 4. See section 9.

9. **Low. Scheduler on `main` does not trade, square off, or back up.** Section 8. `job_news` (`engine/runner.py:97-107`) does not fetch RSS even though `news/scrape.py:51` can. A square-off outage cannot be handled by the current job.

10. **Low. Docs disagree on the database and the front door.** `docs/PLAN.md` (SQLite only, Tailscale only) vs `docs/DECISIONS.md` (Postgres for keys, public HTTP nginx) vs code (both stores, loopback bind, secure cookie default, bootstrap disables the secure cookie).

11. **Low. Login has no rate limit, and the session key can be the admin password.** `web/app.py:65-78`, `web/auth.py:30-32`.

12. **Info. Duplicate settings fields.** `config/settings.py:69-76` repeated at `:100-106`. The later assignment wins. Behaviour matches the second copy.

13. **Info. Account material in a doc, not a key.** `docs/DECISIONS.md` at `1a5971def520229d25453d5a2a5557bcfea488fe` contains live cash and holdings figures and states that TOTP and API credentials were exposed outside git. Rotation is not something this repo can prove.

## Assumptions

- `main` at `aae5f1f` is the tree to audit. Unmerged branches are compared, not checked out.
- "Safe to merge" means: no new broker mutation, no live-flag change, and no scheduled Angel login. Paper-ledger branches fail that bar even though they do not call `placeOrder`.
- The nginx and RDS described in `docs/DECISIONS.md` were not probed. Findings about public HTTP are from the repo, not from a live request.
- A string was treated as a credential only when it was a high-entropy literal or a URL with a password. Code such as `get_secret_value()` was not.

## Known gaps

- No production host was inspected. Whether bootstrap's `COOKIE_SECURE=false` is what the server `.env` contains is unknown.
- Angel login health (the AB1050 episode in DECISIONS) was not re-tested. This audit must not log in.
- Type checking is not part of the project toolchain.
- `feat/v9-plan` stopgap scripts were classified by search, not executed.
