-- C17: idempotent paper jobs per trade_date (fill / scan once per day).
CREATE TABLE IF NOT EXISTS paper_runs (
  trade_date TEXT NOT NULL,
  job TEXT NOT NULL,
  completed_ms INTEGER NOT NULL,
  PRIMARY KEY (trade_date, job)
);
