# Handoff AUD-3 — Baseline audit of NSE-TRADE

## Summary

Read-only baseline of `main` (`aae5f1f2674547083edd2d325db3646e7fe4876e`). The write-up is `docs/audit/nse-baseline.md`. No trading code, settings defaults, or dependencies were changed. No broker, exchange, or deploy command was run.

`main` is a paper-default research tree. Angel place, modify, and cancel exist and refuse unless `mode=live` and `live_orders=true`. The runner does not call them. Nine of eleven scheduled jobs only log. The Nifty 100 universe in git is a small fixture. SQLite holds the trading ledger. Postgres holds keys. Unmerged engine work culminates in `fix/c19-review` and should not be merged until it is rebased and the new Angel login jobs are reviewed. No API key, TOTP seed, or password value is in git history.

## Files changed

- `docs/audit/nse-baseline.md` (added)
- `docs/handoff/AUD-3.md` (this file)

## Commands run and results

Ran 2026-11-06 18:02 IST against `main` before the doc commit, with pinned requirements installed to a temp prefix (not a project dependency change).

| Command | Result |
|---|---|
| `python3 -m ruff check .` | All checks passed, exit 0 |
| `python3 -m pytest -q --tb=line` | 230 passed in 47.55s, exit 0 |
| `python3 -m compileall -q` | exit 0 |

No mypy or pyright config exists (`requirements-dev.txt` is pytest and ruff only). CI does not type-check either.

Branch comparison used `git rev-list`, `git merge-base --is-ancestor`, and `git log` / `git diff --name-only` against `origin/*`. Secret scan used `git rev-list --all` and `git cat-file` and printed only path, commit, and a class. It did not print values.

## Assumptions

- Audit the checked-out `main`. Describe other branches. Do not check them out or merge them.
- "Safe to merge" means no new broker mutation, no live-flag change, and no new scheduled Angel login.
- Nginx and RDS in `docs/DECISIONS.md` were not contacted.
- A line counts as a committed credential only when the literal is a high-entropy secret or a URL with a password. `get_secret_value()` calls do not count.

## Known gaps

- The server `.env` and the live nginx site were not inspected. `COOKIE_SECURE=false` is what `deploy/bootstrap_server.sh` writes. Whether that file is what production uses is unknown.
- Angel login was not retried.
- `scripts/stopgap/` on `feat/v9-plan` was not executed.
- This ticket adds no runtime test. The suite above is the existing tree.

## Security impact

Documentation only. Nothing in the running service changes when this branch is merged.

The audit records existing risk, in `docs/audit/nse-baseline.md` section 15:

- Angel order methods ignore the kill switch (`broker/angel.py:107-133`).
- Bootstrap disables the Secure cookie and the secure-channel check trusts forwarded headers (`deploy/bootstrap_server.sh:31`, `web/secure_channel.py:10-41`).
- Most portal GETs have no admin check.
- `docs/DECISIONS.md` at `1a5971def520229d25453d5a2a5557bcfea488fe` says a TOTP seed and API credentials were exposed outside the repo, and it contains live account figures. Those values are not copied into the audit.
- No committed secret material was found. Empty templates: `.env.example` at `f8841256df78419fdb05c2d86a58a378a15d93d3`, `config/angel.env.example` at `19473d3e0017d24a998ccee4f7449faa8a575b26` and `367917c26f9f1e5cc5962edf4991571f20d152a2`.

## Rollback

```bash
git checkout main
git branch -D jarvis/AUD-3
git push origin --delete jarvis/AUD-3
```

That removes two documentation files. It does not change runtime behaviour on `main`.
