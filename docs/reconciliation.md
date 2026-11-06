# Reconciliation report (NSE-005)

Snapshot: `origin/main` at `aae5f1f` (merge of PR #5, 29 Oct 2026, 13:55 IST), after `git fetch origin --prune` on 6 Nov 2026 (IST). Thirty remote branches besides `main`. Nothing here was merged or deleted.

Ahead / behind is `git rev-list --left-right --count origin/main...branch`: the first number is commits on `main` that the branch does not have (behind), the second is commits the branch has that `main` does not (ahead). A conflict call is `git merge-tree --write-tree --name-only origin/main <branch>` on that snapshot. "Clean" means no textual conflicts with today's `main`. It does not mean the result is safe to deploy.

`docs/phase-reports/SUMMARY.md` still says the V0–V6 stack is unmerged and that its tip is `feat/v6-intraday-shadow`. That was true when the summary was written. Those branches are inside `main` now. The paper pipeline written after that is not.

## Recommendation catalog

Each line is the decision for that branch. Detail follows. Words are only `merge`, `cherry-pick`, or `drop`.

### Already inside main — drop

These tips are ancestors of `aae5f1f`. A merge would add zero commits. `docs/phase-reports/SUMMARY.md` still offers "open a PR" links for them; those links are stale.

- `feat/mvp-backtest-news` — drop. 31 behind, 0 ahead. Tip `f884125`, 23 Oct 2026 18:19 IST. MVP baseline (P0–P4, news module, V2 plan). Diff against `main` is empty.
- `feat/v0-hygiene` — drop. 18 behind, 0 ahead. Tip `ca41788`, 23 Oct 2026 18:32 IST. V0 hygiene, already in `main`.
- `feat/v1-market` — drop. 14 behind, 0 ahead. Tip `b8131ca`, 23 Oct 2026 18:46 IST. Sessions, holidays, corporate actions. Already in `main`.
- `feat/v1b-opening` — drop. 12 behind, 0 ahead. Tip `88a0500`, 23 Oct 2026 18:52 IST. Opening and cue recorder. Already in `main`.
- `feat/v2-lab-fixes` — drop. 11 behind, 0 ahead. Tip `591d59b`, 23 Oct 2026 19:01 IST. Shared exits, baselines, ledger. Already in `main`.
- `feat/v3-research` — drop. 9 behind, 0 ahead. Tip `a385fbb`, 23 Oct 2026 19:05 IST. Bhav downloader, S7, PREREG runner. Already in `main`.
- `feat/v4-paper` — drop. 7 behind, 0 ahead. Tip `79cfa34`, 23 Oct 2026 19:11 IST. Paper book. Already in `main`.
- `feat/v5-portal` — drop. 5 behind, 0 ahead. Tip `dd71ed5`, 23 Oct 2026 19:11 IST. Portal shell and API contracts. Already in `main`.
- `feat/v6-intraday-shadow` — drop. 2 behind, 0 ahead. Tip `1a5971d`, 23 Oct 2026 19:32 IST. Last commit of the merged V-line. `main` is this tip plus the cooldown fix below. The unmerged paper stack forks here.
- `fix/monotonic-cooldown` — drop. 1 behind, 0 ahead. Tip `7e8703f`, 26 Oct 2026 01:40 IST. Merged as PR #5 on 29 Oct 2026 13:55 IST. Cooldowns treat "never" as absent so Test Angel stops looping into HTTP 429.

### One paper stack forked from V6 — merge only the tip

Every branch in this group shares merge-base `1a5971d` (`feat/v6-intraday-shadow`). Each is 2 commits behind `main`. Those two commits are PR #5: the cooldown fix and the merge commit. The same cooldown diff is already on the stack as `f65d933` (identical `git patch-id` to `7e8703f`), which is why a merge into `main` is clean even though the hashes differ.

`git merge-tree` of each of these against `origin/main` is clean. Merging more than the tip would replay the same commits twice and leave the older pull requests (PR #1 through PR #4) based on branches that are not `main`. The tip contains every other branch in this group. Two side branches are not ancestors of the tip; their own lines say so. The tip does not change `mode` or `live_orders` defaults (`paper` / `false` on both sides of the diff).

- `feat/review-v0-v6` — drop. 2 behind, 2 ahead. Tip `1e0b9b7`, 23 Oct 2026 19:45 IST. Docs only: the V0–V6 review and the prompt that starts the fix round. Both commits are inside `fix/c19-review`.
- `feat/v-fix-1` — drop. 2 behind, 21 ahead. Tip `13b4fa6`, 23 Oct 2026 22:01 IST. Review fixes R1–R15: runner jobs, Book B slot count, trusted-proxy gate, real baselines, one intraday trade per symbol per day, Book A context, broker protocol and square-off, S7 rank, PREREG window, daily BarView, ATR trail, Angel websocket loop behind fakes. All of that is inside the tip.
- `feat/v-fix-2` — drop. 2 behind, 26 ahead. Tip `608032d`, 24 Oct 2026 13:38 IST. F1a–F1d: Angel daily bars into the lake, paper scan / fill / outcomes, Book B sector cap, `paper_dry_run`. Open PR #1 targets `feat/v-fix-1`, not `main`. Close that PR when the tip lands; merging it does not update `main`.
- `feat/review-v-fix-2` — drop. 2 behind, 24 ahead. Tip `3619f64`, 23 Oct 2026 22:01 IST. Sibling of `feat/v-fix-2`, not an ancestor of the tip. The only files the tip lacks are `docs/reviews/REVIEW_V-FIX-2-PLAN.md` and a `docs/CURSOR_RUN.md` pointer at that prompt. The code the prompt asked for is already on the stack. Merging this branch would stop at the V-FIX-1 tree plus the prompt and would omit F1 and everything after it. A merge of this branch into the tip is clean, and still not worth doing: the prompt tells an agent to rebuild work that already exists.
- `feat/portal-hubs` — drop. 2 behind, 27 ahead. Tip `1900f6c`, 24 Oct 2026 14:11 IST. Portal hubs (Command, Book, Evidence, System) and the Watchlist page. Inside the tip.
- `feat/v-fix-2-login` — drop. 2 behind, 28 ahead. Tip `e59c72c`, 25 Oct 2026 05:04 IST. Real Angel login path and Nifty 100 instrument refresh in the runner, plus the hubs. Inside the tip. This is also the fork point of `deploy/20261026`.
- `feat/v-next` — drop. 2 behind, 30 ahead. Tip `fcd1d52`, 24 Oct 2026 14:40 IST. N1–N6: daily lake build, PREREG T6 open-entry, sector cap, opening-gap note, a deploy proposal for a non-git server checkout, and a "WIP: paused" commit. Open PR #2 targets `feat/v-fix-1`. Close it with the tip; do not merge it into that old base.
- `feat/v8-news-p0` — drop. 2 behind, 31 ahead. Tip `17edf5e`, 24 Oct 2026 14:45 IST. Hermes-style headline extract and event JSONL refresh. Open PR #3 targets `feat/v-next`. Inside the tip.
- `feat/v8-complete` — drop. 2 behind, 51 ahead. Tip `2e86247`, 29 Oct 2026 14:03 IST. Joins the F1 line with V8: 1-second tick rollup, EMUDHRA symbol, local env sync, FY backfill CLI, the cooldown patch, pre-open JSON shape, RSS fetch, portal vol-rank. Commit `367917c` gitignores `config/angel.env` and tests the sync with dummy values (`k1`, `c1`, `p1`, `t1`); it does not add a filled env file. `config/angel.env` is not in the tree. Open PR #4 targets `feat/v-next`. Inside the tip.
- `deploy/20261026` — drop. 2 behind, 32 ahead. Tip `be3bdc9`, 26 Oct 2026 14:49 IST. Four commits on top of `feat/v-fix-2-login`: cooldown, pre-open shape, portal vol-rank, and "job_news actually fetches". The first three have the same `git patch-id` as commits already on the tip (`f65d933`, `8911314`, `cab6487`). The news commit is the same `news/scrape.py` `fetch_all` change as `bb22ab9` on the tip; the runner hunk differs only because the tip's news job was already richer (event JSONL). Merging this branch into today's `main` is clean and would ship those four fixes without the rest of the paper stack. Merging it and then the tip conflicts in `engine/runner.py` and `web/portal_data.py`. Do not merge it. There is no open PR.
- `feat/c17-paper-book` — drop. 2 behind, 55 ahead. Tip `340d64b`, 30 Oct 2026 03:14 IST. C13 market filter wired into the scan, then C17 paper-book fixes (slots, cash, bar gate, job order, equity sizing, idempotent jobs). Inside the tip.
- `fix/runtime-overrides` — drop. 2 behind, 56 ahead. Tip `0034a49`, 30 Oct 2026 13:17 IST. One fix on top of C17: loading Postgres keys at startup no longer wipes SQLite runtime settings. That commit is inside the tip. See the database section for why `main` still has the wipe.
- `feat/c19-monday-paper` — drop. 2 behind, 60 ahead. Tip `df990f1`, 1 Nov 2026 13:54 IST. C19/T2–T5: quote fallback (quote, then 1-minute bar, then daily lake), Book A intraday paper on 1-minute bars, AB1007 login backoff, health for login / feeds / paper jobs. Inside the tip, which adds two review commits on top.
- `fix/c19-review` — merge. 2 behind, 62 ahead. Tip `e126b3b`, 2 Nov 2026 12:16 IST. This is the branch to take. 149 files, +9980 / −396 versus `main`. It is a clean merge into today's `main`. No pull request targets `main` today (PRs #1–#4 target older stack branches).

What the tip adds, beyond the library code already on `main`:

- The scheduler stops being a set of log lines. Daily bars, paper scan / fill / outcomes, news fetch, instrument refresh, and Book A intraday paper are wired.
- Portal hubs, watchlist, vol-rank, and a health view of login, feeds, and paper jobs.
- Book B sector cap, equity sizing, idempotent paper jobs, and the C19 review of Book A paper equity (wallet plus open P&L; MIS blocks margin and does not debit cash).
- Startup no longer clears SQLite runtime settings when it reads Postgres keys.
- Further SQLite migrations `005_paper_runs.sql`, `006_book_a.sql`, `007_book_a_cursor.sql`. `main` stops at `004_lab_trials.sql`.
- `mode` and `live_orders` stay `paper` and `false`.

Do this only as a reviewed pull request into `main`. Run `ruff check .` and `pytest -q` on the result first. Rebase onto `main` after the jarvis pull requests below if those land first: the tip conflicts with `jarvis/NSE-004`, `jarvis/nse-003`, and `jarvis/NSE-006` (see the order at the end of the branch section). It merges clean with `jarvis/AUD-3` and `jarvis/nse-001`.

`deploy.yml` on `main` is aimed at this tree once it is merged, and that workflow currently fails before SSH (see Deployment). Merging the tip does not by itself restart the server. It also does not by itself turn on live orders. The runner on the tip does call Angel for login, candles, and news. That is a read path, and it is the reason this merge wants a human review rather than a drive-by.

### Docs and stopgaps that are not on the tip — cherry-pick

- `feat/v9-plan` — cherry-pick. 2 behind, 13 ahead. Tip `bff18bd`, 30 Oct 2026 13:18 IST. Thirteen commits, almost all documents: work queue C0–C18, `docs/PLAN_V9_OPTIONS.md`, `docs/CURSOR_NEXT.md`, `docs/research/BACKTEST_2020_2026.md`, `config/events.json`, and a decision log about keeping the news filter off for paper. A merge into `main` is clean. A merge into the tip is not: `docs/DECISIONS.md` conflicts, and `scripts/stopgap/replay_paper.py` is an add/add conflict (the tip already has its own copy).

Cherry-pick the new documents onto whichever line you keep, and resolve `docs/DECISIONS.md` by hand:

- `docs/CURSOR_NEXT.md`
- `docs/PLAN_V9_OPTIONS.md`
- `docs/research/BACKTEST_2020_2026.md`
- `config/events.json`
- the decision-log paragraphs in `docs/DECISIONS.md` that are not already on the tip

Leave the branch itself unmerged. Do not take these scripts onto `main` without a separate review:

- `scripts/stopgap/set_mpin.py` reads the server env and writes `angel_pin` through `save_key`. It is marked as a reference copy. It does not belong in git as a way to change a broker PIN.
- `scripts/stopgap/ws_recorder.py` opens an Angel WebSocket session. The file says it does not place an order. It is still a live broker connection.
- `scripts/stopgap/backfill_today.py` and `scripts/stopgap/backfill_nse_chart.py` call Angel candle reads.
- `scripts/stopgap/live_signals.py` says it never places an order and does not call Angel. It is a shadow scanner over recorder files. Keep it with the recorder review, not in a docs cherry-pick.
- `scripts/stopgap/replay_paper.py` is already on the tip.

### Jarvis pull requests opened 6 Nov 2026 — merge three, drop one

These five branches sit on `aae5f1f` (0 behind). Each merges clean into today's `main`. They do not all merge clean into each other, and three of them do not merge clean into the paper tip. None of them flip `mode` or `live_orders` to on. `jarvis/NSE-006` adds two more flags, `live_orders_enabled` and `live_orders_confirm`, both defaulting to false, and tests that a live send needs every flag.

- `jarvis/AUD-3` — merge. 0 behind, 2 ahead. Tip `5ca7f29`, 6 Nov 2026 18:04 IST. Docs only: `docs/audit/nse-baseline.md` and `docs/handoff/AUD-3.md`. Open PR #6. Clean against `main`, against the paper tip, and against the other four jarvis branches. There is no `docs/audit/` on `main` today; this PR is what adds it.
- `jarvis/nse-001` — merge. 0 behind, 4 ahead. Tip `59b52b7`, 6 Nov 2026 18:14 IST. Dev setup: `Makefile` targets, offline socket guard in tests, CI steps for ruff, pytest, pip-audit, and gitleaks. Open PR #8. Clean against `main`, against `jarvis/nse-003`, against `jarvis/AUD-3`, and against the paper tip. Conflicts with `jarvis/NSE-004` and `jarvis/NSE-006` in `.env.example` and `tests/conftest.py`. Land this before those.
- `jarvis/nse-003` — merge. 0 behind, 3 ahead. Tip `5867aa0`, 6 Nov 2026 18:26 IST. One module for Angel credentials, log redaction, and a gitleaks history note. Open PR #9. Clean against `main` and against `jarvis/nse-001`. Conflicts with `jarvis/NSE-004` and `jarvis/NSE-006` in `broker/angel.py` and `config/settings.py`. Conflicts with the paper tip in `broker/smartconnect_factory.py`, `scripts/login_check.py`, and `web/test_angel.py`. Land it after `jarvis/nse-001` and before `jarvis/NSE-006`, or rebase it onto the tip if the tip lands first.
- `jarvis/NSE-006` — merge. 0 behind, 3 ahead. Tip `8bc6b76`, 6 Nov 2026 18:33 IST. The live-order guard from NSE-004, plus paper and shadow scheduled jobs that the commit message says do not send broker orders (`engine/scheduled_jobs.py`, migration `005_scheduled_jobs.sql`). Open PR #10. The guard files match `jarvis/NSE-004` (empty diff on `broker/live_guard.py`, `broker/angel.py`, `config/settings.py`, `tests/test_live_guard.py`), and a merge of the two jarvis branches is clean. Conflicts with `jarvis/nse-001` (`.env.example`, `tests/conftest.py`) and `jarvis/nse-003` (`broker/angel.py`, `config/settings.py`). Conflicts with the paper tip in `broker/angel.py`, `engine/runner.py`, and `tests/test_state.py`, because both sides grow the scheduler.
- `jarvis/NSE-004` — drop. 0 behind, 2 ahead. Tip `30451d8`, 6 Nov 2026 18:11 IST. Open PR #7. The code change is the live-order guard, and those files are already identical on `jarvis/NSE-006`. Merging both adds nothing. Close PR #7 when PR #10 merges. If PR #10 is rejected, change this line to merge: the guard is the part worth keeping, and it merges clean into today's `main` on its own.

`jarvis/NSE-005` is this report. It did not exist in the snapshot above.

### Order to land, when the owner reviews

1. `jarvis/AUD-3` (PR #6) and `jarvis/nse-001` (PR #8). They do not collide with each other or with the paper tip.
2. `jarvis/nse-003` (PR #9). Resolve it against `jarvis/nse-001` only if that PR moved the same lines; on this snapshot the two merge clean.
3. `jarvis/NSE-006` (PR #10). Resolve `.env.example`, `tests/conftest.py`, `broker/angel.py`, and `config/settings.py` against the two PRs above. Close PR #7 without merging.
4. Open one pull request from `fix/c19-review` into the `main` that contains those three. Resolve `broker/angel.py`, `engine/runner.py`, `tests/test_state.py`, and, because `jarvis/nse-003` landed, `broker/smartconnect_factory.py`, `scripts/login_check.py`, and `web/test_angel.py`. Do not merge PR #1, #2, #3, or #4.
5. Cherry-pick the `feat/v9-plan` documents listed above onto that result. Skip the stopgap scripts.
6. Leave every `drop` branch in place until the owner deletes it. This ticket does not delete branches.

The other order (paper tip first, then rebase the jarvis code PRs) is also clean of surprises against today's `main`, and it collides on the same files. Prefer the jarvis PRs first only because they are small, already have pull requests into `main`, and the paper tip does not. Either order is a review, not an unattended merge. Do not deploy from either until the workflow in the next section is fixed, and not during 09:00–15:45 IST on a weekday.

## SQLite and Postgres

### What each store holds on `main`

SQLite is the engine. `config/paths.py` puts it at `{DATA_DIR}/engine.db`. `DATA_DIR` defaults to `./var`, so the file is `var/engine.db`. `engine/state.py` opens it in WAL mode and applies `engine/migrations/*.sql`.

Tables created or altered on `main`:

| Migration | Tables |
| --- | --- |
| `001_init.sql` | `schema_version`, `instruments`, `sessions`, `signals`, `orders`, `trades`, `daily_pnl`, `events`, `settings`, `lab_trials`, `parity` |
| `002_paper.sql` | `paper_cycles`, `pending_orders`, `holdings` |
| `003_opening.sql` | `global_cues`, `flows`, `headlines`, `preopen_snapshots`, `opening_summary`, `morning_brief`, `sentiment_daily` |
| `004_lab_trials.sql` | adds `prereg_id`, `data_hash`, `post_hoc` on `lab_trials` |

Code that talks to that file:

- `engine/runner.py` opens it in `EngineRunner.__init__` and passes the connection into the web app. The 18:30 backup job only logs "stub job".
- `engine/state.py` is the migration runner and the repository for settings, events, and instruments.
- `lab/ledger.py` records trials in the same file (`lab_trials`).
- `data/flows.py` and `data/global_cues.py` write FII/DII and cue rows.
- `web/portal_data.py` reads it for every portal page.
- `scripts/research.py` defaults `--db` to this file.
- Tests build a temporary copy. They do not open Postgres: they delete `DATABASE_URL` where a test might otherwise see one.

`settings` in SQLite is the runtime override table (portal kill switch and similar). `get_setting` checks that table first, then env `Settings`.

Postgres is the key cabinet, and only when `DATABASE_URL` is set. `storage/pg.py` uses psycopg (sync, not asyncpg) and creates:

- `app_settings` — sealed API keys and a few plain strings (`config/key_fields.py`: Angel, Groq, OpenRouter, HF, Telegram, session secret, expected static IP).
- `app_settings_history` — fingerprint and masked value, not the secret.
- `audit_events` — short audit rows from `/keys`.
- `schema_version` — created, and never inserted by `init_postgres`. It is a different table from SQLite's `schema_version`, on a different server, with the same name.

Call sites:

- `config/secrets_loader.py` `apply_db_secrets` at process start, and `save_key` / `clear_key` from `/keys`. If `DATABASE_URL` is empty it logs "no DATABASE_URL" and returns. Keys then stay on the env `Settings` object.
- `web/keys.py` reads history and writes `audit_events` when a URL is set.
- `deploy/bootstrap_server.sh` calls `init_postgres()` once, after copying a database URL off the crypto engine's env and rewriting the database name to `nse_engine`.
- `engine/runner.py` `start()` calls `apply_db_secrets()` before the scheduler starts.
- `scripts/login_check.py` calls `apply_db_secrets()` before a read-only login check.

`psycopg[binary]==3.2.4` is in `requirements.txt`, so the image always has the driver. Tests never connect.

Bars are a third store and not a database: Parquet under `{DATA_DIR}/lake` (`config/paths.py`). `docs/PLAN.md` A7 describes that split (SQLite for state, Parquet for bars) and says there is no database server. `docs/DECISIONS.md` (23 Oct 2026, "Keys in Postgres") later put keys on the crypto RDS instance, database name `nse_engine`, and left the trading tables in SQLite. Both documents are still in the tree. The code follows the later decision for keys and the plan for everything else.

### The bug the split already causes

On `main`, `init_db` loads SQLite `settings` into the in-memory override map. `start()` then calls `apply_db_secrets()`, which calls `reset_settings_cache()`. That function clears the override map and does not load it again. Postgres key load therefore drops portal runtime settings on every boot. `fix/runtime-overrides` (commit `0034a49`, inside `fix/c19-review`) stops the reset from throwing those overrides away. `main` does not have that commit.

### Single source of truth

The single source of truth is SQLite `var/engine.db`, for this service, including sealed keys. Keep Parquet `var/lake/` as the bar archive. Retire Postgres `nse_engine` after a one-time copy of the key rows.

This is the smaller move. Trading, paper, lab, portal, and tests already use SQLite. Postgres holds about a dozen key rows and an audit log. Research and paper then boot with no RDS. The service stays inside the 600 MB cap without a database client on the hot path. The trading ledger stays off the crypto instance, which is what `docs/SHARED_INFRA.md` and the 23 Oct share-decision already require. The boot wipe goes away because there is no second store to reload.

Assumption, logged because the owner is not here to pick: the 23 Oct choice "keys live in Postgres like crypto" is treated as a deploy convenience, not as a requirement that the trading engine depend on RDS. If that assumption is wrong, use the fallback at the end of this section and do not start the migration.

### Migration plan (owner runs later; this ticket does not)

No step places, cancels, or amends an order. No step points NSE at the crypto database. `mode` and `live_orders` stay at their defaults.

1. Take the runtime-override fix (it arrives with `fix/c19-review`) before relying on portal settings across a restart.
2. Add SQLite tables with the same columns as `app_settings` and `app_settings_history`. Do not reuse the name `settings` (that table is runtime overrides) and do not reuse `schema_version` for key versions.
3. On the server, `SELECT` the Postgres rows. Write the sealed blobs into SQLite. Do not print values. Do not write them into git, logs, or this document.
4. Teach `secrets_loader` to read SQLite first. For one release, if the SQLite row is missing and `DATABASE_URL` is set, read Postgres and copy the row across. Writes go to SQLite only.
5. Confirm `/keys` round-trips (mask and fingerprint only) and that a restart still has both the keys and the SQLite runtime overrides.
6. Remove `DATABASE_URL` from the service environment. Leave the RDS database where it is until the owner deletes it. `bootstrap_server.sh` should stop rewriting the crypto URL.
7. After that release, delete the Postgres read path and drop `psycopg` from `requirements.txt` in a later change. Not in this ticket.

Fallback, if keys must stay on Postgres: do not migrate the trading tables. Keep SQLite as the trading source of truth and Postgres as the key source of truth, and ship `0034a49` so the two loads stop erasing each other. Still do not share `nse_engine` with the crypto database. The duplicate name `schema_version` should be renamed on the Postgres side whenever that schema is next touched, so a dump is not mistaken for the engine file.

## Deployment docs versus the tree

Checked against `main` only. The server itself was not contacted. "Reality" here means the files a deploy would use, plus the one GitHub Actions run this repo recorded for `deploy.yml`.

What matches, so it does not need a rewrite:

- Unit file `deploy/nse-engine.service`: user `ubuntu`, `/home/ubuntu/nse-engine`, `python -m engine.runner`, `MemoryMax=600M`, `Restart=on-failure`, `RestartSec=10`. That matches `docs/PLAN.md` A14 and `docs/SERVER_SETUP.md`.
- Default bind is `127.0.0.1:8090` (`config/settings.py`, `.env.example`, the unit's `EnvironmentFile`).
- Python 3.12 in the README, `pyproject.toml` (`requires-python`), CI, and `deploy/bootstrap_server.sh`.
- Market-hours block Mon–Fri 09:00–15:45 IST, with `workflow_dispatch` input `force`, is in `docs/RUNBOOK.md` and `.github/workflows/deploy.yml`.
- Secret names in the workflow (`EC2_HOST`, `EC2_USER`, `EC2_SSH_KEY`) match `docs/SERVER_SETUP.md` step 6. This report did not read whether those secrets are set.

Mismatches:

1. **What "deployed" means.** `docs/PLAN.md` and `docs/RUNBOOK.md` describe a push to `main` that SSHes, pulls, installs, restarts `nse-engine`, and curls `127.0.0.1:8090/api/health`. The only `deploy.yml` run on `main` is the 29 Oct 2026 13:55 IST push (PR #5). GitHub marks it failed in 0 seconds with the note that the run likely failed because of a workflow file issue, and it recorded no jobs. The `ci` workflow on the same push succeeded. The SSH step is gated with `if: ${{ secrets.EC2_HOST != '' }}`. GitHub Actions does not accept the `secrets` context in an `if` condition, so this step cannot see the secret. A green CI run is not a deploy. Whether the EC2 checkout matches `aae5f1f` is unknown from this repo.

2. **The process `main` would start is still the stub scheduler.** `engine/runner.py` logs "stub job" for login, feed, square-off, backfill, and backup. `job_news` builds an empty headline list and never fetches RSS (the comment says live fetch is optional). `job_free_quotes` does poll. `docs/phase-reports/SUMMARY.md` and the V0–V6 reports describe a built engine. The libraries are on `main`. The clock that would run paper, login, and backups is not. That clock is on `fix/c19-review`. Shipping `main` does not ship the paper stack the later docs talk about.

3. **Who can reach the portal.** `docs/PLAN.md` A13/A14, `docs/SERVER_SETUP.md`, and `docs/SHARED_INFRA.md` say Tailscale only, bind loopback, no public port. `docs/DECISIONS.md` (23 Oct 2026) records nginx on port 80, path `/nse/`, because the security group did not allow 8090, and records a plain-HTTP URL. `docs/PLAN_V2.md` B24 calls that plain HTTP a defect and Q2's default is Tailscale. The code serves both `/` and `/nse/` (`web/portal_shell.py`, `<base href="/nse/">`). There is no nginx config and no Tailscale unit in the repo. `deploy/bootstrap_server.sh` comments "nginx / Tailscale" and then prints a public `:8090/` URL, which is the port the decision log says is closed, and it does not print `/nse/`.

4. **Where secrets live.** `docs/PLAN.md`, `docs/SERVER_SETUP.md`, the README, and `.env.example` tell the owner to type Angel, Telegram, and AI keys into `.env`. `docs/DECISIONS.md`, `storage/pg.py`, and `config/key_fields.py` say those keys go to Postgres through `/keys`, and `.env` holds `DATABASE_URL`, `SECRETS_MASTER_KEY`, `ADMIN_PASSWORD`, and the bind. `deploy/bootstrap_server.sh` follows the decision log: it copies those three values out of the crypto engine's `.env`, rewrites the database name to `nse_engine`, and does not write Angel keys. It also writes `ADMIN_PASSWORD`, while `.env.example` documents `PORTAL_ADMIN_HASH` and leaves `ADMIN_PASSWORD` as a second name. `cookie_secure` defaults to true in `config/settings.py`; the bootstrap file sets `COOKIE_SECURE=false`.

5. **Data directory.** `docs/PLAN.md` says `data/engine.db` and `data/lake/`. The code uses `{DATA_DIR}/engine.db` and `{DATA_DIR}/lake`, and `DATA_DIR` defaults to `./var` so the Python package `data/` is not the database. The README still says research writes `data/reports/` and `docs/SHARED_INFRA.md` says India headlines land in `data/news/`. LLM call logs go to `{DATA_DIR}/llm_calls` (`integrations/llm_client.py`). Bootstrap sets `DATA_DIR=/home/ubuntu/nse-engine/var`, which matches the code and not the plan's `data/` paths. Shared-file env vars (`SHARED_HEADLINES_PATH`, `SHARED_LLM_BUDGET_PATH`) are in the README and `docs/SHARED_INFRA.md`; bootstrap creates `/home/ubuntu/shared` and does not set either variable, so a bootstrapped box stays standalone.

6. **Install tool.** The README says `uv venv` and `uv pip`. There is no `uv.lock`. CI, `deploy.yml`, `docs/SERVER_SETUP.md`, and bootstrap use `python3.12 -m venv` and `pip install -r requirements.txt`. Deploy does not install `requirements-dev.txt` (that part is right). CI installs both files with pip, not uv.

7. **sudoers.** `deploy.yml` runs `sudo systemctl restart nse-engine`. Bootstrap installs a passwordless sudoers drop-in for that. `docs/SERVER_SETUP.md` copies the unit and enables it, and never mentions sudoers. A box built only from `docs/SERVER_SETUP.md` will fail the workflow's restart even after the workflow file is fixed.

8. **Backup.** `docs/PLAN.md` A14 specifies an 18:30 IST `sqlite3 .backup` into `~/backups/nse/`, kept 30 days, plus a lake tar. `job_backup` on `main` logs and returns. No backup script or timer is in `deploy/`.

9. **Repo name and visibility.** `docs/PLAN.md` and the first decision-log entry say a private repo `dhruvparekhdp/nse-engine`. A later entry the same day says the GitHub repo is public `dhruvparekhdp/NSE-TRADE`. The clone path, the unit, and the Python project name are still `nse-engine`. The README title is NSE-TRADE (nse-engine) and its status line still points at `feat/mvp-backtest-news`, which is an ancestor of `main`.

10. **CI does not run on every branch push.** `.github/workflows/ci.yml` runs on push to `main` and `feat/**`, and on every `pull_request`. Pushes to `fix/**`, `deploy/**`, and `jarvis/**` do not start CI unless a pull request is open. `deploy.yml` itself only deploys when `github.ref == refs/heads/main`, so a `workflow_dispatch` from another branch does not deploy either. The market-hours guard is on that same job, which the 29 Oct run never reached.

11. **Server checkout may not be a git clone.** The workflow's remote script is `cd ~/nse-engine && git pull --ff-only`. `feat/v-next` records a deploy proposal for a non-git `~/nse-engine` (commit message N6). If the box was copied without `.git`, the pull cannot fast-forward. This repo cannot see which of those is true.

## Assumptions

- The owner will review and merge later. This document recommends; it does not merge, delete, or deploy.
- "Keys in Postgres" (23 Oct 2026) can be reversed in favor of SQLite without losing a product requirement. The fallback in the database section is the path if that is wrong.
- The EC2 was not inspected. Mismatch 1 and mismatch 11 stay open until someone with access looks, without printing env values.
- `git merge-tree` cleanliness is necessary and not sufficient. The paper tip and the jarvis code branches are each clean against `main` and not clean against each other.
- Dummy values in commit `367917c` (`k1`, `c1`, `p1`, `t1`) are test fixtures, not credentials. No `.env` file is tracked on `main` or on `fix/c19-review`.
- Branch tips and pull-request numbers are the 6 Nov 2026 snapshot. A branch created after the fetch (including `jarvis/NSE-005`) is outside the catalog on purpose.
