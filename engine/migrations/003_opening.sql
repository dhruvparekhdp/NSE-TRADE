-- PLAN_V2 §5 / V1b: opening + sentiment recorder tables. Recording and display only (D8).
-- Additive deviations from §5 (both read by §7 contracts):
--   global_cues.mkt_ts_ms        exchange time of the last trade, so "stale" can be judged without guessing
--   headlines.nifty_move_next_60m  filled in later, once Nifty has had 60 minutes to react (V1b-3)

CREATE TABLE IF NOT EXISTS global_cues (
  ts_ms INTEGER NOT NULL, key TEXT NOT NULL,
  last REAL, chg_pct REAL, ref_close REAL, source TEXT NOT NULL, stale INTEGER DEFAULT 0,
  mkt_ts_ms INTEGER,
  PRIMARY KEY (ts_ms, key)
);

CREATE TABLE IF NOT EXISTS flows (
  trade_date TEXT PRIMARY KEY, fii_net_cr REAL, dii_net_cr REAL, source TEXT, final INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS headlines (
  id INTEGER PRIMARY KEY, ts_ms INTEGER NOT NULL, published_ms INTEGER, source TEXT, title TEXT NOT NULL,
  link TEXT, event_type TEXT, symbol TEXT, score REAL, confidence REAL, market TEXT,
  external_id TEXT UNIQUE, nifty_move_next_60m REAL
);
CREATE INDEX IF NOT EXISTS idx_headlines_ts ON headlines(ts_ms);

CREATE TABLE IF NOT EXISTS preopen_snapshots (
  trade_date TEXT NOT NULL, ts_ms INTEGER NOT NULL, symbol TEXT NOT NULL,
  iep REAL, prev_close REAL, chg_pct REAL, buy_qty INTEGER, sell_qty INTEGER,
  final INTEGER DEFAULT 0, source TEXT,
  PRIMARY KEY (trade_date, ts_ms, symbol)
);

CREATE TABLE IF NOT EXISTS opening_summary (
  trade_date TEXT NOT NULL, symbol TEXT NOT NULL, open REAL, prev_close REAL, gap_pct REAL,
  imbalance REAL,
  or15_high REAL, or15_low REAL, or30_high REAL, or30_low REAL, first5_vol_x REAL,
  gap_filled_ms INTEGER, close REAL, open_to_close_pct REAL, open_type TEXT,
  PRIMARY KEY (trade_date, symbol)
);

CREATE TABLE IF NOT EXISTS morning_brief (
  trade_date TEXT PRIMARY KEY, built_ms INTEGER, json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sentiment_daily (
  trade_date TEXT PRIMARY KEY, composite REAL, parts_json TEXT NOT NULL,
  breadth_adv INTEGER, breadth_dec INTEGER, risk_off_alarm INTEGER DEFAULT 0
);
