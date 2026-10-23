# How the Indian cash market works (reference for the NSE engine)

Written 23 Oct 2026 by Claude (planner) for Cursor (builder) and the owner. This is the market knowledge behind
`docs/PLAN_V2.md`. Where it disagrees with `docs/PLAN.md`, this file is newer. Facts marked **VERIFY** had
conflicting sources on 23 Oct 2026; the owner confirms them (contract note, Angel app, NSE circular) before
paper or live depends on them. Sources are listed at the end.

---

## 1. The pieces

| Piece | What it is | Why the engine cares |
|---|---|---|
| SEBI | The market regulator | Sets the algo rules (§6), margin rules (§3), closing auction (§2) |
| NSE | The exchange we trade on (cash market, "CM" segment) | Sessions, ticks, price bands, bhavcopy, holidays |
| NSE Clearing | Settles trades | T+1 settlement (§3) |
| CDSL | Depository that holds Angel clients' shares | DP charge on every delivery sell day (§5) |
| Angel One | Our broker; SmartAPI is its API | Costs, auto square-off time, static IP, order rules |
| Nifty 50 / Nifty Next 50 | Two indices; together they make the **Nifty 100** (our universe) | Rebalanced twice a year (March and September), so old data needs past members (survivorship, §9) |
| India VIX | Volatility index built from Nifty options | Market-mood feature; candidate market filter |
| GIFT Nifty | Nifty futures on NSE IX in GIFT City, trading almost round the clock (replaced SGX Nifty in July 2023) | Best overnight hint of where Nifty will open |

The cash market is a continuous limit order book: orders match on price, then time. Each stock trades in a
**series**. `EQ` is normal rolling settlement (intraday allowed). `BE`/`BZ` are trade-for-trade (every trade
must be delivered, no intraday). The engine trades `EQ` only. All Nifty 100 stocks are `EQ`.

Most Nifty 100 stocks also have futures and options. That makes them **"F&O stocks"**, and since August
2026 they follow different closing rules from other stocks (§2). The engine must know, per symbol, whether it
is an F&O stock.

## 2. The trading day (IST)

### Pre-open call auction, 09:00–09:15 (changed 7 Sep 2026)

| Time | Phase |
|---|---|
| 09:00–09:05 | Order entry: limit and market orders |
| 09:05–09:10 | Limit orders only. Market orders can't be changed or cancelled. Entry closes **at a random moment between 09:08 and 09:10** |
| 09:10–09:12 | Matching at one equilibrium price, which becomes the day's open |
| 09:12–09:15 | Unmatched orders move into continuous trading |

### Continuous trading and the close: it depends on the date and on the stock

The closing auction session (**CAS**) replaced "close = VWAP of the last 30 minutes" for F&O stocks. Its
timings changed once already:

| Period | F&O stocks (most of the Nifty 100) | Non-F&O stocks |
|---|---|---|
| Before 3 Aug 2026 | Continuous 09:15–15:30. Close = VWAP of 15:00–15:30 | Same |
| **3 Aug 2026 – 6 Dec 2026 (now)** | Continuous **09:15–15:15**. CAS 15:15–15:35: 15:15–15:20 reference price + transition, 15:20–15:25 limit + market entry, 15:25–15:30 limit-only entry (random close 15:28–15:30), 15:30–15:35 matching. **Close = auction price** | Continuous 09:15–15:30. Close = 30-min VWAP |
| **From 7 Dec 2026** (SEBI circular 15 Oct 2026) | Continuous **09:15–15:30**. CAS 15:30–15:40: 15:30 reference price (1 min), 15:31–15:36 limit + market entry, 15:36–15:40 limit-only entry (random close 15:38–15:40). Rules for orders left unfilled change again on 8 Feb 2027 | Unchanged (**VERIFY** that non-F&O stocks still close on VWAP) |
| All | Post-close session 15:50–16:00, trades at the closing price only | Same |

What this means for the engine:

- **Session times are data, not constants.** They need an effective-from date and a stock class (F&O or
  not). `core/clock.py` today assumes a 15:30 close for every stock on every date.
- **Daily bars changed meaning.** For F&O stocks, the daily "close" since 3 Aug 2026 is an auction price. From
  7 Dec it is also set after 15:30. A backtest should flag this regime change (a feature column) and not treat
  the close as a tradable continuous-market price.
- **No 1-minute bars exist after 15:15** for F&O stocks between 3 Aug and 6 Dec 2026. Bar-health checks must not
  count those minutes as missing.
- The engine never trades in the pre-open or the CAS. Book B's next-day entries are placed at or after 09:15.

### Broker auto square-off (MIS), **VERIFY**

Angel One's support page says intraday equity square-off is at **15:15**, but that page predates CAS. Since
3 Aug 2026 brokers moved the cut-off earlier for F&O stocks, to between 15:00 and 15:10 (Fyers 15:05,
5paisa 15:10, JM 15:05, share.market 15:00). One comparison site reports Angel at 15:10 or 15:15. Angel charges
its normal brokerage for auto square-off, with no extra penalty. **The engine's 15:05 square-off (PLAN A3) can
now land after the broker's.** The owner checks the cut-off in the Angel app. The engine then squares off at
least 15 minutes before it (PLAN_V2 V1-3).

### Special sessions 2026

- **Muhurat trading: Sunday 8 Nov 2026, afternoon, not evening.** NSE's notice (reported 19 Oct 2026) gives a
  block-deal window 13:50–14:05, pre-open 14:05–14:15, and continuous trading 14:20–15:15, then CAS. Sources
  disagree on the exact end (15:15 + CAS vs 15:30), so **VERIFY** against the NSE circular.
  `config/holidays_2026.json` has a placeholder of 18:15–19:15, which is wrong. Recommendation: no new entries
  in either book during Muhurat (one thin hour). Book A stays flat.
- The 2026 Union Budget (Sunday 1 Feb) had a special live session. Such days are announced by circular and
  belong in the special-sessions list.

### Holidays 2026 (weekdays the market is shut)

26 Jan, 3 Mar, 26 Mar, 31 Mar, 3 Apr, 14 Apr, 1 May, 28 May, 26 Jun, 14 Sep, 2 Oct, 20 Oct, 10 Nov, 24 Nov,
25 Dec. Some lists add 15 Jan (Maharashtra civic elections). Weekend festivals cause no extra closures. NSE
publishes next year's list around December. **The engine must refuse to trade a year it has no holiday file
for** instead of treating every weekday as open, which is what it does today.

## 3. Products, margin and settlement

| | CNC (delivery), used by Book B | MIS (intraday), used by Book A |
|---|---|---|
| Direction | Long only. Selling shares you don't hold creates a short delivery, which goes to auction with a penalty | Long or short |
| Holding | Overnight, as long as you like | Must be closed the same day, or the broker squares it off |
| Money needed | Full value | Upfront margin of at least VaR + ELM, with a 20% floor, so at most about **5x** leverage. Brokers can't promise fixed leverage. Peak-margin snapshots during the day enforce it |
| Settlement | **T+1**: shares reach the demat account the next trading day. Same-day sale proceeds can usually fund new buys | Netted the same day |
| Costs | STT 0.1% on both sides, stamp 0.015% on the buy, DP charge on the sell day | STT 0.025% on the sell, stamp 0.003% on the buy, no DP |
| Tax | Capital gains (§7) | Speculative business income (§7) |

Buying CNC and selling the same day counts as an intraday trade for STT and tax. Book B must hold for at least one
night. T+0 settlement (optional, limited list) and MTF (margin funding) are out of scope.

## 4. Prices: ticks, bands and surveillance

**Tick size by price band** (NSE, from 15 Apr 2025, reviewed monthly on month-end prices):

| Price | Tick |
|---|---|
| below ₹250 | ₹0.01 |
| ₹250 – ₹1,000 | ₹0.05 |
| ₹1,000 – ₹5,000 | ₹0.10 |
| ₹5,000 – ₹10,000 | ₹0.50 |
| ₹10,000 – ₹20,000 | ₹1.00 |
| above ₹20,000 | ₹5.00 |

A stock's tick can change at a month boundary, so **read `tick_size` from Angel's scrip master every morning**.
This table is only the fallback, and the engine must never assume ₹0.05. An order price off the tick is
rejected.

**Price bands.** Non-F&O stocks have fixed daily bands (2/5/10/20%). F&O stocks have **dynamic** bands: an
operating range (typically 10%) that the exchange widens step by step when price presses against it. They have
no permanent "upper circuit", but you still can't trade outside the current range. The full quote's
upper/lower limits are what the circuit-buffer check must use. Market-wide circuit breakers (10/15/20% moves in
Nifty or Sensex) halt everything.

**Surveillance lists.** ASM (Additional Surveillance Measure) and GSM (Graded Surveillance Measure) put stocks
on higher margins, trade-for-trade or tighter bands. NSE publishes the lists daily. Nifty 100 stocks rarely
appear, but the engine should read the list and exclude anything on it (skip reason `surveillance`).

## 5. What a trade costs at Angel One (Oct 2026)

| Charge | Delivery (CNC) | Intraday (MIS) | Where it's from |
|---|---|---|---|
| Brokerage | lower of ₹20 or 0.1% per executed order, **minimum ₹5** | same | Angel pricing update, effective 17 Nov 2025 |
| STT | 0.1% buy + 0.1% sell | 0.025% sell | Unchanged by Budget 2026, which only raised F&O STT |
| NSE transaction charge | **0.00307%** each side (Angel lists 0.0030699%) | same | Angel and Zerodha tables. The code has 0.00297% (the Oct 2024 rate). **VERIFY** on a contract note |
| SEBI fee | ₹10 per crore each side | same | |
| Stamp duty | 0.015% of buy | 0.003% of buy | |
| GST | 18% of (brokerage + transaction charge + SEBI fee), and on DP | same | |
| DP charge | ₹20 + GST = **₹23.60 per stock per sell day** | none | Angel support page |
| IPFT | 0.0000001%, too small to model | same | |
| Auto square-off | n/a | charged like normal brokerage (no penalty) | Angel charges page |

Some marketing pages still say "₹0 delivery brokerage". Angel's own pricing page says ₹20 / 0.1% with a ₹5
minimum. The first real contract note settles it.

**Round trip, recomputed with these rates** (buy and sell the same value):

| Book | Position | Charges | % of position | + slippage | In R |
|---|---|---|---|---|---|
| MIS | ₹25,000 | ₹56.07 | 0.224% | 0.284% (0.06%) | 0.57R at a 0.5% stop, 0.28R at 1% |
| MIS | ₹50,000 | ₹64.94 | 0.130% | 0.190% | 0.38R / 0.19R |
| MIS | ₹1,00,000 | ₹82.68 | 0.083% | 0.143% | 0.29R / 0.14R |
| MIS | ₹2,00,000 | ₹118.16 | 0.059% | 0.119% | 0.24R / 0.12R |
| CNC | ₹10,000 | ₹69.45 | 0.694% | 0.794% (0.10%) | 0.16R at a 5% stop, 0.10R at 8% |
| CNC | ₹25,000 | ₹126.42 | 0.506% | 0.606% | 0.12R / 0.08R |
| CNC | ₹50,000 | ₹182.04 | 0.364% | 0.464% | 0.09R / 0.06R |

Two consequences that PLAN.md missed:

1. **Book B slot size matters.** PLAN sizes Book B as capital ÷ `max_open_swing`. At ₹50k and 5 slots that is
   ₹10k a position, which costs 0.79% a round trip (the flat ₹23.60 DP charge and the ₹20 brokerage dominate).
   At ₹25k it is ₹5k positions and about 1%. Keep CNC positions at **₹20k or more**: fewer slots, more capital,
   or both (PLAN_V2 V1-4).
2. **Book A can't trade at ₹50k under its own rules.** At 1% risk (₹500) and the ₹1L minimum position, the stop
   must be 0.5% or tighter, which is exactly where costs take 0.29R a trade. The 0.8–1.5% stops PLAN asks for
   need ₹800–1,500 risk, which is 1.6–3% of ₹50k. Book A stays shadow-only until capital and evidence change
   that (PLAN_V2 §2).

## 6. Rules for API (algo) trading, Angel SmartAPI, from 1 Apr 2026

- **Static IP:** API orders are accepted only from the registered primary static IP. A secondary IP can be
  added. The mapped IP can be changed **at most once a calendar week**. Data and login calls are not tied to the
  IP.
- **Order types:** **market and IOC orders are prohibited** for algo orders (some brokers convert market orders
  to market-price-protection orders, but Angel prohibits them). The engine uses LIMIT and STOPLOSS_LIMIT only,
  which PLAN already says.
- **Speed:** a 10 orders-per-second threshold per exchange segment, counting new orders, modifications and
  cancels. Below it no strategy registration is needed and orders carry a generic algo ID. We throttle at 5/s.
- **Login:** one session per trading day with 2FA (client code + MPIN + TOTP). No long-lived refresh tokens.
- **Hosting:** retail algos run on the broker's servers, except "tech-savvy" clients who run their own logic from
  a registered static IP. That is us (EC2 Elastic IP).

## 7. Tax (for the CA export)

- **Delivery (Book B):** short-term capital gains (held 12 months or less) are taxed at **20%**. Long-term gains
  are taxed at **12.5%** above ₹1.25 lakh a year. Budget 2026 didn't change these.
- **Intraday (Book A):** speculative business income, taxed at the slab rate, filed in an ITR-3 style return.
- The **Income Tax Act 2025** replaces the 1961 Act from tax year 2026-27, and section numbers changed. The tax
  export should label rows by category (intraday-speculative / STCG / LTCG / charges split), not by section
  number. The owner's CA maps them.

## 8. What moves Indian large caps (feature ideas, not proven edges)

| Driver | When | Notes for features |
|---|---|---|
| Global cues | Overnight | US close, GIFT Nifty change since 15:30 IST, Asian open |
| FII / DII cash flows | NSE publishes provisional numbers every evening | Foreign selling has driven most big Nifty drawdowns. A flow is known only after the close, so it's a next-day feature (no lookahead) |
| USD/INR, crude oil | Continuous | India imports most of its oil, so crude spikes hurt OMCs, paints, aviation and the rupee |
| RBI policy (MPC) | 6 meetings a year, decision about 10:00 IST | Banks and NBFCs react |
| Union Budget | 1 Feb | Big sector moves. Special session if it falls on a weekend |
| Quarterly results | Jan, Apr, Jul, Oct (within 45 days of quarter end, 60 for Q4) | Gaps of 5–10% are common in large caps. PLAN already blocks entries near results |
| F&O expiry | NSE: **Tuesday**. Monthly stock and index contracts expire on the last Tuesday (since Sep 2025) | Volatility and pinning near expiry in F&O stocks. Add an `expiry_day` feature |
| Index rebalancing | Nifty: semi-annual (Mar/Sep); MSCI and FTSE reviews | Flows into stocks being added and out of those being removed, on the effective day |
| Corporate actions | Ex-dates | Splits, bonuses and dividends create fake gaps in unadjusted data (§9) |

## 8b. The opening: why it matters and what to record (owner, 23 Oct 2026)

In India most of a large cap's daily range is often decided around the open. Overnight news, US and Asian
moves, GIFT Nifty, crude, the rupee and last evening's FII/DII flows all land in one place: the **09:00–09:15
pre-open auction**, then the first 15–30 minutes of trading. The owner's rule: track all of it, every day.

| Window (IST) | What happens | What to record |
|---|---|---|
| Previous evening 18:00 | FII/DII provisional cash flows published. Results and board-meeting outcomes released after 15:30 | FII net, DII net (₹ cr); per-symbol announcements |
| Overnight to 08:45 | US close, US futures, Asia opens (Nikkei 05:30, Kospi 05:30, Hang Seng 06:45 IST), GIFT Nifty trading | S&P 500 / Nasdaq / Dow close %, ES/NQ futures %, **Europe close** (DAX, FTSE 100, CAC 40, Euro Stoxx 50), Nikkei/Hang Seng/Kospi %, USD/INR, DXY, Brent, gold, US 10y, **GIFT Nifty change vs yesterday's Nifty close**, India VIX close, overnight headlines with event tag and sentiment score |
| During the Indian session | Europe opens about 12:30 IST (summer) / 13:30 IST (winter). US data at 18:00–19:00 IST. US futures trade all day | Europe live %, US futures live %, Brent and USD/INR live, breaking headlines (war, tariffs, central banks) with time stamps so their effect on Nifty can be measured afterwards |
| 09:00–09:08/10 | Pre-open order entry, random close | Per stock and for Nifty: indicative equilibrium price (IEP), change vs previous close, total buy and sell quantity (the imbalance), snapshots every 30 s |
| 09:10–09:15 | Matching; the open is fixed | Final open price = official open; gap % per stock and for Nifty |
| 09:15–09:45 | Opening drive | Opening range (15 and 30 min), first-5-min volume vs its 20-day average, gap filled or not (and when), breadth (advancers vs decliners in the Nifty 100), sector moves |
| By 15:30 | Did the open predict the day? | Open-to-close return, close vs opening range, **opening type** label: gap-up-and-go, gap-up-fade, gap-down-recover, gap-down-go, flat |

**Major-event news to tag** (extends `news/india_rules.py`, which already has rbi_policy, budget, sebi,
election, war, fed, inflation, earnings, fii_dii, credit_rating, banking_stress, commodity): `geopolitics_india`
(border, Pakistan, China), `middle_east` (Iran, Israel, Red Sea, Hormuz; it moves crude, which India imports),
`russia_ukraine`, `tariffs_trade` (US tariffs and trade deals), `us_data` (CPI, payrolls, GDP), `china`,
`opec`, `monsoon` (IMD), `gst_council`, `india_macro` (CPI, IIP, GDP), `block_deal`, `promoter_pledge`. Each
headline keeps its source, time, tag, symbol hint and score. **Risk-off alarm** (information only): a
war/geopolitics headline **and** Brent up 3% or more **and** India VIX up 10% or more within the same 2 hours →
red banner on the portal and one Telegram alert.

Two warnings from the crypto engine. First, news sentiment there simply echoed price (the market-news score
followed BTC's 24 h move 48 times out of 48). Second, no filter improved the swing book. So the opening record
starts as **information and research data**, not a trade filter, until the lab shows lift. The data itself is
precious: pre-open snapshots and live breadth can't be downloaded afterwards, so recording starts as early as
possible.

Free sources (all unofficial; **VERIFY** each and expect breakage): NSE website JSON for pre-open
(`/api/market-data-pre-open?key=NIFTY` and `key=FO`) and FII/DII (`/api/fiidiiTradeReact`), which need a
browser-like session cookie. Yahoo chart API for US/Asia indices, futures, USD/INR (`INR=X`), Brent (`BZ=F`),
Nifty (`^NSEI`) and India VIX (`^INDIAVIX`). GIFT Nifty has no reliable free API (NSE IX website or a paid
feed). Until one is found, US futures plus Asia stand in as the overnight proxy. Angel's WebSocket gives live
LTP and quotes from 09:15. Whether it streams indicative prices during the pre-open is **VERIFY**.

## 9. Data: what to use, and the traps

| Need | Source | Traps |
|---|---|---|
| Instruments, tokens, tick sizes | Angel scrip master JSON (daily) | Tick sizes are in paise. Ticks change monthly |
| Daily OHLCV, research history | NSE **bhavcopy** | Since July 2024 the file is the **UDiFF** format (`BhavCopy_NSE_CM_0_0_0_YYYYMMDD_F_0000.csv.zip`, new column names such as `TckrSymb`, `SctySrs`, `OpnPric`, `ClsPric`; Cursor checks the exact headers against a real file). The legacy format applies only to older dates. The parser in `data/history.py` reads only legacy columns |
| Delivery quantity | NSE "full bhavcopy with delivery" (`sec_bhavdata_full_DDMMYYYY.csv`, **VERIFY** the name) | A separate file from the price bhavcopy |
| Split / bonus / dividend adjustment | NSE corporate actions, or the yfinance adjusted close (research only) | **Bhavcopy and the Yahoo chart API are unadjusted.** A 1:1 bonus looks like a −50% gap and fires every stop in a backtest. Keep raw prices and an adjustment factor |
| Index members over time | niftyindices.com constituent lists + NSE index-change notices | Backtesting today's Nifty 100 over 2012–2026 inflates results (survivorship) |
| 1-minute history | Angel `getCandleData` | Users report a 500-candle cap per request and AB1021 throttling. P1-3 measures the real depth |
| Live ticks, bid/ask | Angel WebSocket V2, SnapQuote mode | Up to 1,000 tokens per connection |
| Live quotes for paper marking | Angel `ltpData` / full quote | The Yahoo chart API (current `data/free_quotes.py`) is delayed, unofficial and can disappear. It's fine for a ticker tape, not for fills |
| India VIX, Nifty history | NSE historical index data / Angel index tokens | |
| FII/DII flows | NSE daily report | Provisional at 18:00, final later |
| Surveillance lists, holidays, circulars | NSE website | |

## 10. Base rates and strategy evidence

- **SEBI study (FY 2022-23):** 71% of individual intraday traders in the cash segment lost money. Among those
  making more than 500 trades a year, it was 80%. Under-30s did worst (76%). Costs were a large part of it.
- **The owner's crypto engine:** intraday direction was a coin flip (walk-forward AUC 0.52). The only lasting
  edge was multi-day breakouts (+0.35R a trade after fees over 5 years). AI judgement and news filters never
  improved it.
- **Momentum in India:** academic work finds both time-series and cross-sectional momentum in Indian stocks after
  standard risk adjustments, with sharp crashes in crisis and recovery phases. NSE's Nifty200 Momentum 30 index
  (6- and 12-month volatility-adjusted momentum, rebalanced twice a year) has led other large-cap indices on
  rolling returns. It also had the deepest drawdowns, including about −30% from Sep 2024 to Mar 2025.
- **Post-earnings drift:** mixed. Older, longer studies (2002–2011) find drift, especially after bad news. A
  smaller 2014–2018 study finds none. Treat it as a hypothesis to test, not an edge.
- **Conclusion for the design:** keep the crypto lesson. Daily-bar swing or momentum on liquid large caps is
  where an edge is plausible and costs are smallest per unit of risk. Intraday stays a shadow experiment
  until it passes the gate.

## 11. Glossary

CNC: delivery product. MIS: intraday product. CAS: closing auction session. VaR / ELM: value-at-risk and
extreme-loss margins. DP charge: depository fee on a delivery sell. STT: securities transaction tax.
Bhavcopy: NSE's daily price file. UDiFF: NSE's unified file format (since 2024). ASM / GSM: surveillance lists.
T+1: settlement one trading day after the trade. Tick: the smallest price step. Static IP: the one IP address
allowed to send API orders. TOPS: threshold orders per second (10). GIFT Nifty: offshore Nifty futures.

## Sources (checked 23 Oct 2026)

- Angel One pricing update, Nov 2025: https://www.angelone.in/news/product-updates/pricing-update-nov-2025-b2c
- Angel One charges (transaction, DP, auto square-off): https://www.angelone.in/exchange-transaction-charges
- Angel One square-off timings: https://www.angelone.in/support/your-orders/square-off
- Angel One SmartAPI changes from 1 Apr 2026: https://oga-prod.angelone.in/news/market-updates/what-s-changing-in-angel-one-s-smartapi-access-from-april-1-2026
- Angel One on the CAS from 3 Aug 2026: https://www.angelone.in/news/market-updates/sebi-closing-auction-session-from-august-3-2026-new-timings-and-rules-for-f-o-stocks
- Zerodha bulletin, CAS and pre-open phases: https://zerodha.com/marketintel/bulletin/439989/introduction-of-closing-auction-session-cas-in-the-equity-cash-segment-and-certain-modifications-in-the-pre-open-auction-session
- SEBI 15 Oct 2026 CAS revision (via TaxGuru): https://taxguru.in/?p=1091029
- Broker square-off times after CAS: https://onetradejournal.com/brokers/auto-square-off-times-and-charges , https://fyers.in/notice-board/introduction-of-the-closing-auction-session-cas-as-per-sebi-guidelines/
- Muhurat 2026: https://www.angelone.in/news/market-updates/muhurat-trading-on-november-8-2026-timings-of-bse-and-nse , https://www.businesstoday.in/markets/stocks/story/muhurat-trading-2026-nse-bse-announce-diwali-timings-check-full-schedule-562486-2026-10-19
- Holidays 2026: https://www.sahi.com/blogs/nse-trading-holidays-2026-complete-list-of-stock-market-holidays , https://www.bajajbroking.in/nse-holidays
- STT after Budget 2026: https://support.zerodha.com/category/account-opening/resident-individual/ri-charges/articles/how-is-the-securities-transaction-tax-stt-calculated , https://groww.in/blog/what-is-stt
- NSE transaction charges table: https://support.zerodha.com/category/account-opening/resident-individual/ri-charges/articles/exchange-transaction-charges
- Tick sizes from 15 Apr 2025: https://zerodha.com/marketintel/bulletin/408151/revision-in-tick-size-for-nse-derivatives-and-cash-segment-from-april-15-2025 , https://www.angelone.in/news/market-updates/nse-revises-tick-size-for-stocks-and-indices-from-april-15-what-traders-need-to-know
- Expiry day (Tuesday): https://moneylife.in/article/nse-equity-fo-contracts-to-expire-on-tuesdays-bse-on-thursdays-from-1st-september/77434.html
- Margins / leverage: https://www.angelone.in/knowledge-center/mtf/what-is-peak-margin , https://www.bajajfinserv.in/sebi-new-margin-rules-intraday-trading
- Surveillance: https://nsearchives.nseindia.com//web/mediaattachment/2026-08/FAQs_-_Additional_Surveillance_Measure_ASM_20260812103311.pdf , https://support.zerodha.com/category/trading-and-markets/trading-faqs/articles/what-does-gsm-mean
- UDiFF bhavcopy: https://www.nseindia.com/static/resources/forms-formats-members , https://tradingqna.com/t/has-nse-changed-bhavcopy-location/169551
- SmartAPI candle limits (forum): https://smartapi.angelone.in/smartapi/forum/post/13202
- SEBI intraday study: https://www.business-standard.com/markets/news/7-in-10-intraday-traders-in-equity-cash-suffered-losses-in-fy23-sebi-study-124072400975_1.html
- Capital gains 2026: https://www.vestai.io/learn/capital-gains-tax-stocks-india , https://www.patronaccounting.com/blog/capital-gains-rules-2026-fmv-holding-period
- Momentum and earnings drift in India: https://ideas.repec.org/a/sae/vision/v19y2015i1p25-36.html , https://ideas.repec.org/a/eme/jefasp/jefas-08-2021-0159.html , https://journals.vutbr.cz/index.php/trends/article/view/541 , https://www.niftyindices.com/Factsheet/Factsheet_Nifty200_Momentum30.pdf , https://arthgyaan.com/fund/icici-prudential-nifty-200-momentum-30-index-fund-direct-growth/150452
