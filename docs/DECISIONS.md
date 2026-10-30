# Decisions log

## 2026-10-23 — Owner decisions (from plan A1)

- Broker: **Angel One SmartAPI** (not Zerodha/Kite).
- Live capital later: ₹25k–₹1 lakh.
- Universe: **Nifty 100**.
- Repo: private GitHub `dhruvparekhdp/NSE-TRADE` (plan named `nse-engine`; this repo is the home).
- Runs as a second service on existing AWS EC2 (t3.small, Sydney `ap-southeast-2`).
- Paper first; real orders only after evidence gates + written owner yes.
- Books: A = intraday MIS, B = delivery swing CNC; evidence decides which goes live first.

## 2026-10-23 — Supersedes earlier Zerodha draft

The `india_equity_engine/` notes under crypto-signal-engine (Zerodha/Kite, Nifty-50) are **not** the build
spec. `docs/PLAN.md` (Trading Systems Plan, 23 Oct 2026) is the source of truth.

## 2026-10-23 — Holidays file

`config/holidays_2026.json` seeded from NSE/BSE 2026 equity holiday circulars. Includes Muhurat trading
on 2026-11-08 (timings TBD by circular). **Owner must verify** against the live NSE holidays page before
relying on it in paper/live.

## 2026-10-23 — Owner: complete plan + news/foreign sentiment

Owner asked to implement the full plan so evening Angel keys unlock backtests immediately, and to add **news / foreign sentiment** (not in original A10), because “half of Indian moves are news and foreign sentiment.”

Decisions:
- Build P1–P4 + Angel order plumbing (P5 methods) now; **live_orders stays false**; no real orders without written yes.
- News module lives in `news/` as **features + optional risk filter**, off by default (`news_filter_enabled=false`). Same proof bar as AI: must show lift in lab before enabling on paper.
- Sources (free, no heavy ML on server): NSE corporate announcements calendar / results window, FII–DII cash flows (when available), US overnight proxies (ES/NQ/SPX, USDINR, India VIX), rule-based headline tags. No LLM required for v1.
- Book B daily backtests can start tonight from bhavcopy/yfinance fixtures even before Angel 1m history is deep.

## 2026-10-23 — MVP build complete locally

Implemented on `feat/mvp-backtest-news`: costs/risk/orders/paper, S1–S6, lab+ledger, lake/bhav/Angel wrappers,
news module (off by default), portal health/lab/books, Angel order methods behind dual live flags.
Synthetic demo: `S6_swing` on SBIN produced 45 trades (negative avg R on synth — expected; not an edge).
Real bhavcopy + Angel keys tonight replace synth for honest Book B numbers.

## 2026-10-23 — Share crypto setup (AI, news, keys, not trading DB)

Owner: use most of the same setup as crypto — AI usage, news scraping, and share similar data between projects.

Decision (see `docs/SHARED_INFRA.md`):
- **Share:** Groq/OpenRouter/HF Space keys + Space endpoints, optional shared `headlines.jsonl` and `llm_budget.json`,
  Tailscale/EC2 host, patterns (ask_json, FinBERT classify, RSS → score).
- **Do not share:** trading SQLite, paper wallets, order state, strategy code.
- NSE implements thin ports under `integrations/` + `news/scrape.py` / `news/pipeline.py` (not a git submodule yet).
- Crypto can later append macro rows to `SHARED_HEADLINES_PATH` with `"market": "crypto"`; NSE appends `"market": "india"`.

## 2026-10-23 — Keys in Postgres + deploy on same EC2

Owner: prefer DB keys like crypto (not .env for API keys); use crypto PEM; deploy on same server; new Postgres DB; give port.

Done:
- RDS database **`nse_engine`** on the same host as crypto (`crypto-postgres…rds.amazonaws.com`).
- Server `.env` holds only infra: `DATABASE_URL`, `SECRETS_MASTER_KEY` (shared with crypto), `ADMIN_PASSWORD`, `PORT` — Angel/AI keys via **`/keys`** → encrypted `app_settings`.
- systemd **`nse-engine`** on **:8090** (internal). Public access via nginx on **:80** path **`/nse/`** (SG did not allow 8090; 80 already open).
- Access: `http://52.62.37.4/nse/` and `http://52.62.37.4/nse/keys` (same admin password as crypto).

## 2026-10-23 — Owner: Claude plans, Cursor builds; NSE engine becomes the crypto engine's twin

Owner: "make it similar in UI, paper trading and basic concept, only market related things will change" and
"Claude plans everything in detail, Cursor does the hard work".

Recorded (details in `docs/PLAN_V2.md`, market facts in `docs/MARKET_INDIA.md`, designed overview and every page
mockup in `docs/blueprint/NSE_Engine_Blueprint.pdf`):
- `docs/PLAN_V2.md` amends `docs/PLAN.md`; where they disagree PLAN_V2 wins. Phases V0–V7 (+ V1b), one branch each.
- Review found 27 issues (B1–B27), several critical: intraday shorts never stopped, gap stops filled at the stop,
  fabricated mirror/random baselines, paper MIS P&L never reaching cash, four intraday strategies that can't fire,
  sessions not CAS-aware (3 Aug 2026), Muhurat 2026 timing wrong, keys typed over plain HTTP.
- Portal: **7 pages, not 21** (owner: "cut them short to only required or club them"): Today, Market mood, Paper book,
  Signals, Evidence, Health, Settings, in crypto's four hubs and design.
- **Opening & sentiment recorder** (owner: "market opening is a very big thing, so track entire sentiment with GIFT
  Nifty, US and Europe market, war news, every major thing"): phase V1b, recording + display only; never a trade
  filter until a pre-registered lab trial shows lift.
- Proposed, awaiting owner confirmation (PLAN_V2 §11): Book B paper first on EOD data (D1); Book A shadow only (D2);
  paper capital ₹1,00,000 with min CNC position ₹20,000 (D3); square-off 15 min before the broker cut-off (D4).

## 2026-10-23 — Angel read-only check (server, 17:10–17:26 IST)

Owner allowed read-only server access. Script piped over SSH (nothing written on the server), keys read in a read-only
Postgres transaction, no orders, no tokens printed. Result: login refused **AB1050 "Invalid totp and client
combination"** twice (secret valid base32, server clock +0.5 s), once skipped (saved secret had a non-base32 symbol).
Funds and holdings not reachable until the TOTP secret saved on /keys is the one issued for client code AA***14.
Stopped retrying to avoid an account lockout. Owner to re-issue TOTP and ask for one more check (PLAN_V2 Q13).
Follow-up (17:36 IST): the stored TOTP secret's fingerprint matches the key on the owner's enable-totp page, and the owner
confirmed the client ID and API key belong to the same profile. A third read-only login still got AB1050. Remaining suspects: the MPIN on
/keys (SmartAPI forum: AB1050 when the password field isn't the current 4-digit MPIN), a temporary block after repeated failures, or
TOTP not active on the account. No further attempts until the owner verifies the MPIN.
Follow-up (17:39 IST): owner re-typed the MPIN (saved 17:38 IST); fourth read-only login, this time via the current base URL
apiconnect.angelone.in (`root=` override, nothing installed on the server), still AB1050. All four keys were freshly saved
(17:22–17:38 IST) and the TOTP secret matches the enable-totp page. Our side is verified as far as it can be without Angel.
Stopped: owner to raise it with Angel SmartAPI support (TOTP active for this client? API login blocked after failed attempts?).
No further attempts today.
Follow-up (17:44 IST): owner changed the MPIN (saved 17:43 IST); fifth read-only login via apiconnect.angelone.in, still AB1050.
The MPIN was not the cause. Stopped for today; next step is the owner's browser test on Angel's publisher login, then Angel support.
Follow-up (17:5x IST): owner shared Angel's login docs. Compared the SDK's actual request with them (captured without sending): URL,
headers and body match, except the old SDK declares a hard-coded `X-ClientPublicIP: 106.193.147.98` and `X-ClientLocalIP: 127.0.0.1`.
One login with the real headers (public 52.62.37.4 = registered static IP, private 172.31.x.x): still AB1050. Every input and the
request format are now verified, so the cause is on Angel's side (TOTP for this client, or a block after failed attempts). The
header fix is added to ticket V0-7 for live orders. No further attempts until Angel support answers (smartapi@angelone.in).
Follow-up (18:1x IST): owner re-issued TOTP (first saved the 6-digit code by mistake, caught before any login), then saved the long
key. One login with correct IP headers: still AB1050. Seven Angel refusals today with every input re-done by the owner. Stop until
Angel support (smartapi@angelone.in) confirms TOTP is active for the client and any lock is cleared.

## 2026-10-23 — Owner: push to the public repo knowingly

`dhruvparekhdp/NSE-TRADE` is **public** on GitHub (checked 23 Oct 2026), although PLAN A14.3 and the first
DECISIONS entry say private. Owner was told that pushing publishes the server IP, the /nse/keys admin URL (plain
HTTP), the server bootstrap script and the blueprint's list of weaknesses (B24), and chose to push anyway.
Consequence for the plan: V0-2 (portal off plain HTTP; keys only over HTTPS/Tailscale) is urgent, and no secret
or production data may ever be committed (AGENTS rule 2 applies doubly to a public repo).
Resolved cause (19:05 IST): owner's Mac login succeeded from Mumbai AND through an SSH tunnel exiting from the Sydney
server (so location/static IP is not the problem). Saved client code, API key and MPIN match what the owner typed
(hash compare); the TOTP secret on /keys is the OLD key (the one shown in the owner's first screenshot), while
TOTP had been re-issued at ~18:05 IST, which invalidated it. Fix: save the current key on /keys. Lesson for V0-8:
show when TOTP was last re-issued vs saved, and Compare would have caught this in seconds. Also: the SDK printed
the API key, client ID and MPIN to the owner's terminal on a failed request (V0-7 log fix); owner to clear the
terminal and rotate the MPIN (and ideally the API key) after the server login works.

## 2026-10-23 — CORRECTION: the Angel AB1050 failures were caused by Claude's test script

Server login now **works** (19:3x IST): login, funds (₹0.89), 3 holdings (value ₹9,323, P&L −₹1,124.20), 0 positions, logout.
Earlier conclusions in this log ("Angel's side", "old TOTP key", "location") were **wrong**. Root cause: Claude's read-only
check script copied the server `.env` (which sets `TZ`) into `os.environ` after Python had started. pyotp's first time
conversion then used the stale timezone and produced a wrong TOTP; the script asked for exactly one code per run, so every
server attempt sent a wrong code (reproduced with a dummy key: first code wrong, later codes right). The owner's keys were
correct apart from two bad pastes that were caught before any login (a 6-digit code, a key with a stray symbol).
The engine itself is not affected today (systemd sets TZ before the process starts), but TOTP must be generated from an
aware UTC datetime so it can never happen (ticket V0-9). No support email to Angel is needed.
Still to do (owner): clear the terminal; rotate the MPIN and API key, which were printed to the terminal by the SDK's error log
during one test, and re-issue the TOTP key, which was shared in chat; save the new values on /keys and run Test Angel once.

## 2026-10-25 — Options on news (BTST / STBT) and delta hedging: paper research only

Owner: "in my 8 years of stock market trading i always like btst for options ... depending on repo rate news or other
news", "btst or stbt both", "even add delta hedging concept in system and also add backtest". Decision: new phase V9
(`docs/PLAN_V9_OPTIONS.md`), modelled on the crypto engine's `analysis/vol_book.py`: Nifty (weekly, Tuesday expiry) and
Bank Nifty (monthly only since Nov 2024) ATM options around scheduled events, unhedged and delta-hedged with index
futures, plus sell vs buy hedged-straddle paper books. No order code path in any V9 module; no change to `mode` /
`live_orders`. Work queue for Cursor: `docs/CURSOR_NEXT.md`.
Also found: `config/policy_dates.json` holds the 2025 RBI MPC dates labelled 2026 (ticket C3).

## 2026-10-30 — Paper Book B with the market filter off; first paper week

Owner (30 Oct, in chat): "no paper trade in this first week, atleast generate some trade, then we can decide all
things of filter". Decisions taken by Claude under that instruction:
- Deployed `feat/c17-paper-book` (340d64b: C11 + C13 + C17) during market hours at 13:10 IST (owner: "do all changes
  now before closing of market"). Backups `~/nse-engine.bak-20261030`, `~/nse-engine-db-20261030.sqlite`,
  `~/crontab.bak-20261030`.
- `market_filter = "off"` saved in engine.db `settings` (paper only; live + off is refused by validate_setting). Every
  pick taken this way stores `would_skip_reason` (today: `market_filter_f1_vol`, Nifty vol rank 0.85), so the take/skip
  comparison stays possible. This is NOT the PREREG rule; results from these trades are paper evidence only and are
  not lab results (AGENTS rule 6).
- The 29 Oct scan was re-run once with the filter off to queue orders for 30 Oct (BHARTIARTL 11, ADANIPORTS 11, DLF 29,
  KOTAKBANK 44); signals were not re-stored. Event `paper_backfill_queue` in engine.db.
- Bug found and fixed on the way (`fix/runtime-overrides`, 0034a49, deployed 13:17 IST): `apply_db_secrets()` at engine
  start called `reset_settings_cache()`, which wiped every SQLite runtime setting (market_filter, kill_switch,
  max_open_swing). Cursor: merge it into `feat/c17-paper-book`.
Revisit the filter after the first paper weeks (owner).
