# Pre-registered research trials (PLAN_V2 V3-2)

**Committed before any trial run.** Changing a rule after seeing results is a new trial and must be flagged `post_hoc=1`.

Halves: **2012-01-01 → 2018-12-31** / **2019-01-01 → 2026-12-31** (Book B daily). Capital ₹1,00,000. Costs from `config/costs_angel.json` (CNC). Gate: n ≥ 100/half, avg R ≥ +0.10 both halves, beats mirror and random both halves, avg R > 0 under cost stress ×1.5.

## Trials

| prereg_id | Strategy | Rule (literal) |
|---|---|---|
| T1_S6_swing | S6_swing | PLAN A10 swing breakout as written; fills via `core/exits` (V2) |
| T2_S6b_keltner | S6b_keltner | PLAN A10 Keltner variant as written; same fill engine |
| T3_F1_vol | S6_swing + F1 | Skip new entries when Nifty 30-day realised-vol rank vs its history > 0.667 (crypto “top third” port) |
| T4_F2_trend | S6_swing + F2 | Skip new entries when Nifty close < 200-day SMA |
| T5_S7_xsmom | S7_xsmom | First trading day of each month: rank `universe_on(date)` by mean of z-scores of 6m and 12m return ÷ daily-return volatility (Nifty200 Momentum 30 style); hold top N = floor(capital / min_position_cnc_inr); exit when holding falls out of top 2N at rebalance or 3×ATR20 safety stop |

## Book A

Only if 1m history depth exists (V6-4 / P1-3). Expected: **none** until Angel history is measured — no Book A gate claimed in V3.

## Defaults (§11)

- `market_filter=off` until a trial passes the gate with a filter on
- Strategies stay disabled in `settings.strategies_enabled` until the owner enables them for paper

## Integrity

- Every run recorded in `lab_trials` with `prereg_id`, `data_hash`, `post_hoc`
- No parameter search on the full sample; no reporting the tune window as OOS
