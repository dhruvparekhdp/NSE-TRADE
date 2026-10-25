# PLAN V9: options on news (BTST / STBT) and a delta-hedged vol book, PAPER ONLY

Owner, 25 Oct 2026: "in my 8 years of stock market trading i always like btst for options ... depending on repo rate
news or other news ... more than 50% of market work on news", "btst or stbt both", "even add delta hedging concept in
system and also add backtest". Crypto twin: `crypto-signal-engine/analysis/vol_book.py` (sell vs buy straddle books,
delta re-hedged inside a 0.10 band). This phase never sends an order: there is no order code path in any V9 module.

## 1. The ideas in plain English

**BTST / STBT on options.** Buy an at-the-money Nifty call (BTST, bullish) or put (STBT, bearish) near the 15:25
close the day before a scheduled news event (RBI policy, FOMC, Budget, election result), sell it the next morning
or next close. The bet: the news moves the index more than the option's overnight time decay costs.

**Delta hedging.** An ATM call gains about 0.5 rupee per rupee the index rises (its *delta*). Short that many
Nifty futures and a small move in either direction cancels out. What is left is a pure bet on the *size* of the
move (gamma) against time decay (theta) and the change in implied volatility after the news (vega). A hedged
straddle (call + put) answers one question: **did the index move more than the options priced in?**
- Buy the hedged straddle: wins when the move is bigger than priced (surprise days).
- Sell the hedged straddle: earns the decay when the move is smaller than priced (most days, and usually after a
  scheduled event, when implied volatility collapses: the "IV crush").

Worked example (Black-Scholes, Nifty 25,000, 7 days to expiry, IV 14%): ATM call ₹208, delta 0.53. Next day
unhedged / hedged: flat -8% / -8%; +0.5% +27% / -5%; +1% +68% / +5%; +2% +166% / +39%. The hedged straddle's
break-even is an overnight move of about 0.85%, which is the bar every event has to clear.

## 2. Backtest results (round 1, 25 Oct 2026; diagnostic, NOT a gate result)

Full numbers: `docs/research/BACKTEST_2020_2026.md`. In short:
- Nifty options are priced rich: VIX implied 1.08% a day vs 0.84% realised, every year 2020-26.
- Selling a delta-hedged straddle for one day still loses (-5% of premium net): rare overnight gaps (+4.8%, -5.0%)
  cannot be hedged, and re-hedging every 0.10 delta costs 3-4% of premium. Never use the 1-day-to-expiry weekly.
- Buying the hedged straddle pays only on big scheduled shocks: Budget (+15.8% avg, n=8), election results, exit polls.
- BTST ATM call into RBI day, exit at the next open (before the 10:00 decision): +7.6% vs +0.1% on ordinary nights,
  positive in both halves. Budget-day put: +22%. FOMC: no directional edge.
- These become the pre-registered V9-3 trials: wider band (0.20), next-weekly expiry, sell-to-expiry with a wing
  (iron fly), event long-vol on Budget / election / exit poll, RBI BTST call exit at open.

## 3. What to build (tickets for Cursor, branch `feat/v9-options`)

### V9-1 `core/options.py` (pure, shared by lab and engine, plan rule 5)
- `bs_price`, `bs_greeks(S, K, T, iv, r, call) -> delta, gamma, theta/day, vega/vol-pt`, `implied_vol(price, ...)`
  (bisection, 1e-6), `round_premium(px)` to the NFO tick 0.05.
- `next_expiry(index, day)`: Nifty weekly expiry is Tuesday (holiday -> previous trading day); Bank Nifty has
  MONTHLY expiry only (no weeklies since Nov 2024), last Tuesday of the month. Read real expiries from the NFO scrip
  master when available; this function is the fallback for backtests.
- Lot sizes come from the scrip master `lotsize` field, never hard-coded.
- Tests: put-call parity to 1e-6; delta equals the numeric derivative; IV round trip; tick rounding; expiry on a
  holiday-shifted Tuesday.

### V9-2 `core/costs.py`: `fo_costs(side, premium_turnover | fut_turnover, kind)`
- Angel F&O: ₹20 per executed order flat; STT options 0.15% of premium on sell, futures 0.05% on sell (Budget 2026
  rates; put them in `config/costs_angel.json` under `"nfo_opt"` / `"nfo_fut"` with the source date); exchange
  charges (options on premium, futures on notional), SEBI ₹10/crore, stamp on buy, GST 18% on brokerage + charges.
- Tests against one hand-worked contract note per kind.

### V9-3 `lab/vol_backtest.py` (+ ledger entries)
- Port the scratch `delta_hedge.py` and `btst.py`: BTST/STBT call / put / straddle / trend, unhedged and
  delta-hedged, exits at the next open and the next close; dynamic re-hedge on 1-min index bars where they exist.
- Every variant is a trial in `lab/ledger.py`. Pre-register in `docs/PREREG.md` BEFORE the run: events list,
  strike rule, IV source, band 0.10, costs, exits. Report the number of variants tried next to every result.
- Gate before any paper capital is assigned: n ≥ 30 events per family, average net > 0 after costs in BOTH halves
  (2019-2022 / 2023-2026), beats the same trade on ordinary nights, survives costs × 1.5.

### V9-4 `engine/vol_book.py`: paper vol book, mirror of crypto (`vol_book_enabled=False` by default)
- Books: `sell` and `buy`, NIFTY weekly ATM straddle, 1 lot each (Bank Nifty monthly as a second underlying).
- Open 15:20 IST on each trading day (BTST timing) and, separately, on the event calendar only (`event` tag).
- Check every 5 min 09:20-15:25: mark legs at mid (Angel `getMarketData` FULL on NFO tokens), Greeks from Angel
  `optionGreek` (fallback `core.options`), re-hedge with the current-month NIFTY future when
  |net delta| > 0.10 × lot. Record the hedge both fractional (the clean number) and whole-lot (what you can really
  trade: with one straddle lot the hedge only moves in whole futures lots, so it is coarse).
- Exit next session 15:20 (or at the chosen exit from the backtest); settle at intrinsic if past expiry.
- Margin shown, not enforced: SPAN + exposure for the short straddle (≈ ₹2-2.5 L per Nifty lot) so the owner sees
  the capital a real version needs.
- Tables (`engine/migrations/00x_vol.sql`): `vol_positions`, `vol_hedges`, `vol_marks` (UTC epoch ms, plan rule 7).
- Test: the module does not import the order client or `engine.orders` (an import-graph test), so it can never
  send an order. No change to `mode` / `live_orders`.

### V9-5 Portal: "Vol book" panel on the Paper book page and an "Events" strip on Today
- Open straddles with strike, expiry, net delta, gamma, theta/day, vega; hedge trades; P&L split into option,
  hedge, costs. Cumulative sell vs buy line. Implied vs realised move per day (bar pair).
- Today: the next scheduled event (from the V8 news/event calendar), its implied move (ATM straddle / spot) and
  the backtest's historical average move for that event type.

### V9-6 Event calendar
- `config/events.json` with RBI (decision: cut/hike/hold, VERIFY 2019-2024 against RBI press releases), FOMC,
  Budget, election, exit polls, US CPI. Times in IST. The V8 news pipeline adds unscheduled shocks later.

## 4. Risks
- Option prices in the backtest are modelled (BS with India VIX), not real quotes. The real ATM IV around events
  often sits above VIX before the event and drops after it, so the model may misstate both legs. V9-4 records real
  quotes from day one so the model can be checked.
- Overnight gaps cannot be hedged (no night session), so "delta-hedged BTST" is still exposed to the gap.
- Selling straddles has unlimited loss on a shock (e.g. 4 Jun 2024 election result day, Nifty -5.9%). Paper only;
  any real version needs a defined-risk structure (iron fly) and its own plan.
- Many variants are tried, so some will look good by chance. The ledger trial count and both-halves rule are the guard.
