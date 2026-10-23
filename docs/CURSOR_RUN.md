# Cursor: run the whole dev plan (paste everything inside the box into a new Cursor Agent chat)

If the chat stops or its context resets, open a new chat and paste the same box again: Cursor resumes from
`docs/phase-reports/PROGRESS.md`.

```
You are the builder for the NSE engine. Claude is the planner and reviewer; I (Dhruv) am the owner.
Run the whole development plan in docs/PLAN_V2.md, phase by phase, without stopping between phases unless a
STOP rule below fires.

READ FIRST, and again at the start of every phase (your context will reset during this long run):
1. docs/phase-reports/PROGRESS.md if it exists: it says where you are. Resume from the first unticked ticket.
2. AGENTS.md: rules that never bend.
3. docs/PLAN_V2.md: §2 decisions, §3.3 bugs B1-B27, §4 files, §5 data model, §6 settings, §7 API, §8 pages,
   §9 phases and tickets, §11 owner questions WITH DEFAULTS (use the defaults; don't wait for me).
4. docs/MARKET_INDIA.md: market facts. Anything marked VERIFY stays a config value, never a constant.
5. docs/PLAN.md: the original spec. PLAN_V2 wins where they disagree.
6. docs/blueprint/NSE_Engine_Blueprint.html: the UI mockups for all 7 pages (exact look, sections, callouts).
7. Reference app, READ-ONLY, never modify it: /Users/dhruv/personal/Tennis-bet/crypto-signal-engine
   (scheduler/portal/ core.js, portal.css, portal.html, nav.js, chrome.js, hubs/*.js; docs/PORTAL_REVAMP.md;
   tests/test_portal.py; analysis/paper_cycle.py, analysis/regime_gate.py, analysis/swing_book.py).

ORDER: V0 -> V1 -> V1b -> V2 -> V3 -> V4 -> V5 -> V6. Do NOT start V7 (it can send real orders; it needs my
written yes).

GIT
- Start with `git fetch && git checkout feat/mvp-backtest-news && git pull`. The baseline (all MVP code + docs +
  docs/blueprint/) is already committed and pushed there by the owner (23 Oct 2026). Its CI is red only because
  of the 2 ruff errors that V0-1 fixes.
- V0-1: on feat/v0-hygiene (from feat/mvp-backtest-news) fix the 2 ruff errors; make sure a PR
  "MVP baseline" (feat/mvp-backtest-news -> main) exists.
- PRs: use `gh pr create` if `gh` is installed and logged in. If not, just push the branch and write the
  "open a PR" link (https://github.com/dhruvparekhdp/NSE-TRADE/pull/new/<branch>) in the phase report and in
  PROGRESS.md; I'll open it.
- Each phase: create feat/v<N>-<topic> FROM THE PREVIOUS PHASE'S BRANCH (stacked; I merge later in order).
  One commit per ticket, message "V1-3: <what>". Push. Open a PR whose base is the previous phase's branch.
- Never push to main, never merge anything, never force-push, never rewrite history.
- Never deploy, never ssh to the server, never touch systemd, nginx or the production database.

EVERY TICKET
1. Write the failing test first (use the test cases written in the ticket, and the probes in §3.3). Run it and
   see it fail.
2. Make the smallest change that passes. Match the existing style; plain-English docstrings that say WHY and
   cite the plan section.
3. `ruff check .` and `pytest -q` green before moving on.
4. Update docs/phase-reports/PROGRESS.md: one line per ticket (id, status, commit hash, note). Create it on
   the first ticket with every ticket from §9 V0-V6 listed as todo.

END OF EVERY PHASE
docs/phase-reports/V<N>.md: what was built, test count, the acceptance numbers, defaults used from §11,
anything still VERIFY, open questions. Push, open the PR, then continue straight to the next phase.

HARD RULES
- settings.mode and settings.live_orders defaults never change; nothing in code or tests sets them; Angel
  order methods stay behind both flags.
- No secrets anywhere: code, tests, fixtures, logs, commits, PR text. Fixtures are fake or scrubbed.
- No network in tests. Scripts may use the network.
- Pre-registered strategy rules and parameters never change. If a rule is ambiguous, use the most literal
  reading and write it in the phase report.
- Every order price rounded to the tick. LIMIT and STOPLOSS_LIMIT only. No MARKET, no IOC.
- V1b (opening and sentiment) is recording and display only: it must never block, size or time a trade.
- The server has 2 GB RAM and a 600 MB limit: no heavy ML libraries in requirements.txt.
- The real portal never shows simulated numbers: empty states instead.

STOP AND ASK ME ONLY IF
- a test can't be made to pass after 3 honest attempts, or passing it would need a pre-registered rule change;
- something needs a secret, a real Angel call, the server, a deploy, or a real order;
- V3: NSE blocks the downloads (I'll download files by hand), or the data has gaps you can't explain;
- the plan contradicts itself in a way the §11 defaults don't settle.
Otherwise keep going.

PHASE NOTES
- V0: includes V0-6 (Test Angel button), V0-7 (smartapi-python 1.5.5, real X-ClientPublicIP / LocalIP / MAC
  headers, `state` in the login body) and V0-8 (keys page: masked value, keyed fingerprint with none for the
  MPIN, compare, reveal with password + 30 s + audit + rate limit, masked history). Test all Angel code with a
  fake SmartConnect. Angel login is blocked right now (AB1050, waiting on Angel support): never try it live.
- V1: config/sessions.json exactly as MARKET_INDIA §2 (F&O stocks: CAS 15:15-15:35 from 3 Aug to 6 Dec 2026;
  continuous to 15:30 and CAS 15:30-15:40 from 7 Dec 2026). Muhurat 8 Nov 2026 is in the afternoon. The holiday
  loader refuses a year it has no file for.
- V1b: sources in config/cues.json; NSE website JSON with browser-like headers and a stale flag on every
  source; Yahoo symbols as listed in V1b-1; GIFT Nifty falls back to the proxy.
- V2: first turn the §3.3 probes into failing tests (B1 short never stopped, B3 gap stop, B5 fake baselines,
  B7 paper cash), then build core/exits.py and make lab/backtest.py use it.
- V3: commit docs/PREREG.md in its own commit BEFORE any trial runs. Download bhavcopy from 2012 to today
  (UDiFF and legacy), at most 1 request every 2 s, resumable. Run the 5 trials, record every run in the
  ledger, write V3.md with the gate table and a plain-English verdict per trial. Don't enable any strategy:
  I decide.
- V4: strategies_enabled stays empty by default, so Book B runs as shadow until I enable a strategy. The
  30-fixture-day end-to-end test must show 0 differences between paper and backtest.
- V5: port crypto's micro-UI; exactly the 7 pages in PLAN_V2 §8, matching the blueprint mockups; a fixture for
  every endpoint; port crypto's structural portal tests; phone width 375 px with no horizontal scroll.
- V6: Angel WebSocket and bar recording behind fakes; Book A shadow only.

WHEN V6 IS DONE
Write docs/phase-reports/SUMMARY.md: each phase with its PR link and test count, what is verified, and what
still needs me (Angel login, a contract note for costs, the 2027 holiday file, the GIFT Nifty source, the §11
questions). Then stop.

AFTER REVIEW V0–V6 (V-FIX rounds)
- V-FIX-1: `feat/v-fix-1` — prompt in docs/reviews/REVIEW_V0-V6.md §5; report docs/phase-reports/V-FIX-1.md.
- V-FIX-2 (next): read docs/reviews/REVIEW_V-FIX-2-PLAN.md (F1–F7 + owner checklist). Branch `feat/v-fix-2`
  after V-FIX-1 merges to main. Planning doc lives on `feat/review-v-fix-2` until merged.
```

## Owner checklist before pasting

- Cursor: Agent mode, the strongest model available, terminal commands allowed in this repo.
- Optional: `brew install gh` then `gh auth login`, so Cursor can open PRs itself. Without it, Cursor pushes
  branches and lists the links for you to open each PR in the browser.
- Keep the Mac awake and on power; this is many hours of work.
- Watch progress in `docs/phase-reports/PROGRESS.md`. Send each PR to Claude for review before merging; merge
  in order: MVP baseline → V0 → V1 → V1b → V2 → V3 → V4 → V5 → V6.
