-- Last finished minute the Book A paper driver processed, per trade date (C19 review: live bars arrive after the minute).
CREATE TABLE IF NOT EXISTS book_a_cursor (
  trade_date TEXT PRIMARY KEY,
  last_minute_ms INTEGER NOT NULL
);
