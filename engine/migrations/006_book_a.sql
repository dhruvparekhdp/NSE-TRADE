-- Book A paper wallet (separate from Book B) + signal execution state (C12/C19).
ALTER TABLE paper_cycles ADD COLUMN book TEXT NOT NULL DEFAULT 'B';
CREATE TABLE IF NOT EXISTS book_a_signal_state (
  signal_id INTEGER PRIMARY KEY,
  status TEXT NOT NULL,
  skip_reason TEXT,
  trade_id INTEGER,
  updated_ms INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS login_guard (
  day TEXT PRIMARY KEY,
  key_version_ms INTEGER NOT NULL DEFAULT 0,
  ab1007_streak INTEGER NOT NULL DEFAULT 0,
  blocked INTEGER NOT NULL DEFAULT 0
);
