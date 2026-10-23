# Shared infra with crypto-signal-engine

Owner decision (23 Oct 2026): reuse the **same operational setup** as crypto — AI providers,
HF Space (FinBERT + embed), news scraping patterns, Telegram style, Tailscale portal, EC2 box —
and **share read-only intelligence data** where it helps. Trading ledgers stay separate.

## What we share

| Piece | How |
|--------|-----|
| Groq / OpenRouter / HF Space keys | Same env names on the server (or copy from crypto `/keys` into NSE `.env`). Never commit. |
| HF Space `dhruvdp/dhruv-llm` | NSE calls `/v1/classify` (FinBERT) and optionally `/v1/embed` — same Space crypto uses. |
| LLM free-tier budget | Optional shared file `SHARED_LLM_BUDGET_PATH` so both engines don’t double-burn the quota. Default: NSE-local `data/llm_budget.json`. |
| Macro / global headlines | Crypto already scrapes + scores. NSE can **read** a headlines export at `SHARED_HEADLINES_PATH` (JSONL). |
| India equity headlines | NSE scrapes its own RSS (Moneycontrol / ET / NSE) into `data/news/`. |
| Telegram | Separate bot recommended (noise isolation); same library pattern. |
| EC2 + Tailscale | Second systemd unit `nse-engine`; portal `:8090` via Tailscale (crypto stays `:8080`). |

## What we do **not** share

- SQLite/Postgres trading DBs, paper wallets, order books
- Strategy code / cost models (equity ≠ crypto)
- Auto-deploy coupling (NSE deploy stays its own workflow; still blocked in market hours)

## AI policy (same as crypto lessons)

- Every call through `integrations/llm_client.ask_json` + budget.
- AI / news **filter off by default**; must prove lift in `lab/` before paper enable.
- Log successful calls under `data/llm_calls/` for later fine-tune (same idea as crypto).

## Server layout (suggested)

```
/home/ubuntu/
  crypto-signal-engine/     # existing
  nse-engine/               # this repo
  shared/
    headlines.jsonl         # crypto appends macro; NSE reads + appends India
    llm_budget.json         # optional shared budget
```

Set in NSE `.env`:

```
HF_BASE_URL=https://...
HF_SPACE_API_KEY=...
GROQ_API_KEY=...
OPENROUTER_API_KEY=...
SHARED_HEADLINES_PATH=/home/ubuntu/shared/headlines.jsonl
SHARED_LLM_BUDGET_PATH=/home/ubuntu/shared/llm_budget.json
```

Until those paths exist, NSE runs fully standalone with rules-only news scoring.
