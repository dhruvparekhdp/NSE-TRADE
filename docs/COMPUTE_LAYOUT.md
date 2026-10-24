# Compute layout (Mac + ThinkPad + EC2)

Owner pattern (same as crypto): **split backtests and extra strategy work** across machines on **Tailscale**. NSE does not need the ThinkPad for live trading; EC2 stays the scheduled paper/live host.

## Roles

| Machine | NSE use | Crypto parallel |
|--------|---------|-----------------|
| **Mac** | Cursor dev, pytest, small lake slices, PRs, portal tweaks | Primary dev |
| **ThinkPad (Tailscale)** | **Heavy backtests**, full `run_prereg_trials`, `build_lake`, event studies, news LLM batch (`refresh_news_scores --llm`), optional **local LLM** experiments | Extra backtest / strategy compute |
| **EC2 (Tailscale)** | `nse-engine` systemd, paper jobs, `/keys`, Angel **order** IP, shared `headlines.jsonl` | Crypto `:8080`, Postgres |

## ThinkPad setup (once on tailnet)

```bash
git clone …/NSE-TRADE.git && cd NSE-TRADE && git checkout feat/v8-complete
python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt
./scripts/sync_local_env.py
mkdir -p var/local && cp config/angel.env.example var/local/angel.env   # fill Angel keys
export DATA_DIR=$PWD/var   # fast disk with room for var/bhav + var/lake
./scripts/start_local_stack.sh
```

**Worker jobs (run on ThinkPad, not Mac):**

```bash
.venv/bin/python -m scripts.build_lake --bhav var/bhav --lake var/lake
.venv/bin/python -m scripts.run_prereg_trials --lake var/lake --trials T1,T2,T3,T4,T5,T6
.venv/bin/python -m scripts.run_fy_angel_backfill --symbols EMUDHRA
.venv/bin/python -m scripts.run_strategy_tests --prereg --lake var/lake
```

Copy results back via gitignored `var/reports/*.json` / `prereg_v3.json` or rsync `var/reports/` to Mac for docs updates.

## Angel keys

- **EC2:** `/keys` portal → Postgres `nse_engine.app_settings` (preferred for server).
- **Mac / ThinkPad:** `var/local/angel.env` (four `ANGEL_*` lines) — never commit.
- After adding keys: `.venv/bin/python -m scripts.login_check` must print `1 LOGIN : True` (no secrets in log).

## Local LLM (ThinkPad)

Use the same Groq/OpenRouter/HF Space keys as crypto (`docs/SHARED_INFRA.md`). Optional: point experiments at a **local** model via Tailscale only for **research** prompts — do not enable `news_filter_enabled` until lab lift is proven.
