# Rules for AI coding agents (Cursor, Claude) - read fully before every task

Project: NSE equity engine on Angel One SmartAPI. Source of truth: docs/PLAN.md. Decisions: docs/DECISIONS.md.

1. Work on a branch feat/<phase>-<topic>; open a PR; never push to main; never deploy during
   market hours (Mon-Fri 09:00-15:45 IST).
2. No secrets anywhere in code, tests, fixtures, logs, commits or chat. Keys come only from .env as SecretStr.
   Strip tokens from recorded fixtures.
3. Every change has a test that fails before and passes after. `ruff check .` and `pytest -q` green before review.
   Tests never touch the network.
4. Real orders require settings.mode == "live" AND settings.live_orders == True. Both default to off. Never change
   these defaults; never set them in code or tests. Any change that can send a real order must be called out at the
   top of the PR description in capital letters.
5. Strategies, costs and risk are pure functions shared by the backtester and the live engine. No duplicate logic.
6. Research results come only from lab/evaluate.py and are counted in lab/ledger.py. Never tune on the full history
   and report the same history. Changing a rule after seeing results is a new trial, flagged post-hoc.
7. Store times as UTC epoch ms; schedule and display in IST (Asia/Kolkata). No naive datetimes.
8. Round order prices to the instrument tick size. Use LIMIT / STOPLOSS_LIMIT orders only. Throttle orders to 5/s.
9. Plain-English docstrings that say WHY (cite the plan section). Small functions. Match existing style.
10. The service must stay under 600 MB RAM. No heavy ML libraries on the server.
11. If something in docs/PLAN.md is unclear or seems wrong, stop and ask the owner; record the answer in
    docs/DECISIONS.md with the date.
12. End every phase with docs/phase-reports/Pn.md: what was built, tests, acceptance numbers, open questions.
