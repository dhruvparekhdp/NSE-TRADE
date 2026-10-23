-- PLAN_V2 V4-1: paper book tables (numbered 002; applied even if 003/004 already ran)
CREATE TABLE IF NOT EXISTS paper_cycles (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  started_ms INTEGER NOT NULL,
  ended_ms INTEGER,
  starting_wallet REAL NOT NULL,
  target_wallet REAL,
  wallet REAL NOT NULL,
  peak_wallet REAL NOT NULL,
  status TEXT NOT NULL DEFAULT 'running',
  outcome TEXT,
  config_json TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS pending_orders (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  trade_date TEXT NOT NULL,
  symbol TEXT NOT NULL,
  book TEXT NOT NULL,
  strategy TEXT NOT NULL,
  side INTEGER NOT NULL,
  qty INTEGER NOT NULL,
  limit_price REAL NOT NULL,
  stop REAL,
  target REAL,
  signal_id INTEGER,
  status TEXT NOT NULL DEFAULT 'pending',
  created_ms INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS holdings (
  symbol TEXT PRIMARY KEY,
  qty INTEGER NOT NULL,
  avg_price REAL NOT NULL,
  bought_ms INTEGER NOT NULL
);
