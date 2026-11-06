-- Paper/shadow scheduled jobs (plan A12 / V4 / V6).
-- One row per key so a re-run updates in place and cannot double-count.
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS quote_snapshots (
  trade_date TEXT NOT NULL,
  symbol TEXT NOT NULL,
  source TEXT NOT NULL DEFAULT 'cache',
  ltp TEXT NOT NULL,
  volume INTEGER NOT NULL DEFAULT 0,
  ts_ms INTEGER NOT NULL,
  PRIMARY KEY (trade_date, symbol, source)
);

CREATE TABLE IF NOT EXISTS job_runs (
  job TEXT NOT NULL,
  idempotency_key TEXT NOT NULL,
  trade_date TEXT NOT NULL,
  result_json TEXT NOT NULL,
  ran_ms INTEGER NOT NULL,
  PRIMARY KEY (job, idempotency_key)
);

CREATE TABLE IF NOT EXISTS performance_snapshots (
  trade_date TEXT NOT NULL,
  book TEXT NOT NULL,
  mode TEXT NOT NULL,
  realized_inr TEXT NOT NULL,
  costs_inr TEXT NOT NULL,
  trades INTEGER NOT NULL,
  as_of_ms INTEGER NOT NULL,
  PRIMARY KEY (trade_date, book, mode)
);
