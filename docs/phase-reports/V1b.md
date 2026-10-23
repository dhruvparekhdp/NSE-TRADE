# V1b — opening and sentiment recorder

Branch: `feat/v1b-opening` (stacked on `feat/v1-market`)  
PR: https://github.com/dhruvparekhdp/NSE-TRADE/pull/new/feat/v1b-opening  
Tests: **109 passed**, `ruff check .` clean.

## Built

| Ticket | What |
|---|---|
| V1b-1 | `config/cues.json` + `data/global_cues.py` (Yahoo chart, stale = 2× interval); `data/flows.py` + NSE session helper; GIFT proxy when `gift_nifty_source=none` |
| V1b-2 | `data/preopen.py` parse + `final=1` marker; fixtures |
| V1b-3 | MARKET_INDIA §8b event tags; `news/headlines_store.py` dedupe; `headlines` table (+ `nifty_move_next_60m`) |
| V1b-4 | `engine/opening.py` opening types, risk-off (all three conditions), morning brief builder |
| V1b-5 | `/api/opening`, `/api/sentiment`, `/api/headlines` empty-safe contracts |
| V1b-6 | `signal_opening_features` — 10:00 never sees 15:45 `open_type` |

Migration `003_opening.sql` (V4 paper tables will use `002` via set-based migrate). Recording only — never a trade filter.

## Defaults used (§11)

- `opening_tracker_enabled=true`, `preopen_snapshot_s=30`, `cues_poll_s=300`
- `risk_off_brent_pct=3`, `risk_off_vix_pct=10`, `risk_off_window_min=120`
- `gift_nifty_source=none`

## Still VERIFY / owner

- Yahoo symbol delays per cue; NSE pre-open / FII-DII endpoints and cookies
- Whether Angel streams IEP in pre-open
- Real GIFT Nifty source (Q11)

## Open questions

None that block V2. Continuing to `feat/v2-lab-fixes`.
