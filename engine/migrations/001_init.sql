-- Plan A7.1 — initial schema. Append-only for events/signals/trades history.
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_version (
  version INTEGER PRIMARY KEY,
  applied_ms INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS instruments (
  symbol TEXT PRIMARY KEY,
  token TEXT,
  trading_symbol TEXT,
  name TEXT,
  isin TEXT,
  tick_size REAL NOT NULL DEFAULT 0.05,
  lot_size INTEGER NOT NULL DEFAULT 1,
  in_universe INTEGER NOT NULL DEFAULT 0,
  updated_ms INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
  trade_date TEXT PRIMARY KEY,
  login_ok INTEGER NOT NULL DEFAULT 0,
  login_ms INTEGER,
  feed_ok INTEGER NOT NULL DEFAULT 0,
  error TEXT
);

CREATE TABLE IF NOT EXISTS signals (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts_ms INTEGER NOT NULL,
  trade_date TEXT NOT NULL,
  symbol TEXT NOT NULL,
  book TEXT NOT NULL,
  strategy TEXT NOT NULL,
  side INTEGER NOT NULL,
  role TEXT NOT NULL,
  price REAL,
  stop REAL,
  target REAL,
  features_json TEXT,
  decision TEXT NOT NULL,
  skip_reason TEXT
);

CREATE TABLE IF NOT EXISTS orders (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  client_tag TEXT NOT NULL UNIQUE,
  broker_order_id TEXT,
  trade_id INTEGER,
  symbol TEXT NOT NULL,
  side TEXT NOT NULL,
  qty INTEGER NOT NULL,
  order_type TEXT NOT NULL,
  product TEXT NOT NULL,
  purpose TEXT NOT NULL,
  price REAL,
  trigger REAL,
  status TEXT NOT NULL,
  filled_qty INTEGER NOT NULL DEFAULT 0,
  avg_price REAL,
  placed_ms INTEGER,
  updated_ms INTEGER,
  mode TEXT NOT NULL,
  error TEXT
);

CREATE TABLE IF NOT EXISTS trades (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  signal_id INTEGER,
  symbol TEXT NOT NULL,
  book TEXT NOT NULL,
  strategy TEXT NOT NULL,
  side INTEGER NOT NULL,
  qty INTEGER NOT NULL,
  entry_ms INTEGER,
  entry_price REAL,
  stop_init REAL,
  stop_now REAL,
  target REAL,
  exit_ms INTEGER,
  exit_price REAL,
  exit_reason TEXT,
  gross_inr REAL,
  costs_inr REAL,
  net_inr REAL,
  r_mult REAL,
  mode TEXT NOT NULL,
  status TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS daily_pnl (
  trade_date TEXT NOT NULL,
  mode TEXT NOT NULL,
  book TEXT NOT NULL,
  start_inr REAL,
  realized_inr REAL,
  costs_inr REAL,
  end_inr REAL,
  trades INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (trade_date, mode, book)
);

CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts_ms INTEGER NOT NULL,
  kind TEXT NOT NULL,
  json TEXT
);

CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value_json TEXT NOT NULL,
  updated_ms INTEGER NOT NULL,
  updated_by TEXT
);

CREATE TABLE IF NOT EXISTS lab_trials (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts_ms INTEGER NOT NULL,
  strategy TEXT NOT NULL,
  params_json TEXT,
  data_from TEXT,
  data_to TEXT,
  period TEXT,
  n INTEGER,
  avg_r REAL,
  win_pct REAL,
  passed INTEGER,
  report_path TEXT
);

CREATE TABLE IF NOT EXISTS parity (
  trade_date TEXT NOT NULL,
  mode TEXT NOT NULL,
  book TEXT NOT NULL,
  signals_live INTEGER,
  signals_replay INTEGER,
  matched INTEGER,
  avg_fill_diff_pct REAL,
  faults_json TEXT,
  PRIMARY KEY (trade_date, mode, book)
);