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
