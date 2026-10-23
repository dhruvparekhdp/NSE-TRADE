# Development summary (PLAN_V2 V0–V6)

Stop here: **V7 (live orders) needs the owner's written yes.** Do not merge to main or deploy during market hours without review.

## Stack (merge in order)

| Phase | Branch | PR | Tests (approx) |
|---|---|---|---|
| MVP baseline | `feat/mvp-backtest-news` | https://github.com/dhruvparekhdp/NSE-TRADE/pull/new/feat/mvp-backtest-news | — |
| V0 hygiene | `feat/v0-hygiene` | https://github.com/dhruvparekhdp/NSE-TRADE/pull/new/feat/v0-hygiene | 73+ |
| V1 market | `feat/v1-market` | https://github.com/dhruvparekhdp/NSE-TRADE/pull/new/feat/v1-market | 87 |
| V1b opening | `feat/v1b-opening` | https://github.com/dhruvparekhdp/NSE-TRADE/pull/new/feat/v1b-opening | 109 |
| V2 lab | `feat/v2-lab-fixes` | https://github.com/dhruvparekhdp/NSE-TRADE/pull/new/feat/v2-lab-fixes | 119 |
| V3 research | `feat/v3-research` | https://github.com/dhruvparekhdp/NSE-TRADE/pull/new/feat/v3-research | — |
| V4 paper | `feat/v4-paper` | https://github.com/dhruvparekhdp/NSE-TRADE/pull/new/feat/v4-paper | +paper cash |
| V5 portal | `feat/v5-portal` | https://github.com/dhruvparekhdp/NSE-TRADE/pull/new/feat/v5-portal | 224 |
| V6 Book A shadow | `feat/v6-intraday-shadow` | https://github.com/dhruvparekhdp/NSE-TRADE/pull/new/feat/v6-intraday-shadow | +late ticks |

Tip of stack: `feat/v6-intraday-shadow` (includes V0–V5).

## Verified in code

- Dual live gate defaults unchanged (`mode=paper`, `live_orders=False`)
- No secrets in repo; portal bind 127.0.0.1; Secure cookies
- Tick rounding, session regimes, CalendarMissing, min ₹5 brokerage, CNC floor
- Opening recorder is display-only (never sizes trades)
- Shared `core/exits.py` for lab fills / gap stops / trails
- PREREG.md committed before trial runner
- PaperBroker credits MIS P&L − costs (B7)
- Portal §7 empty-safe contracts (92 portal API tests)

## Still needs the owner

1. **Angel login** (AB1050 / TOTP): save current TOTP on /keys; rotate MPIN after server login works  
2. **Contract note** to set `verified_against_contract_note: true` on costs  
3. **`holidays_2027.json`** before Jan 2027  
4. **GIFT Nifty source** (`gift_nifty_source`)  
5. **Bhav backfill**: `python -m scripts.download_bhav --from 2012-01-01 --to <today>` then re-run `scripts.run_prereg_trials` and paste the gate table into `V3.md`  
6. **Enable strategies** in paper only after a trial passes (`strategies_enabled`)  
7. **§11 questions** still VERIFY (broker square-off, NSE unofficial endpoints, Angel pre-open IEP)  
8. **Phone check** of portal at 375px  
9. **V7 written yes** before any live order path

## Phase reports

`docs/phase-reports/V0.md` … `V6.md` and `PROGRESS.md`.
