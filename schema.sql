CREATE TABLE IF NOT EXISTS gold_prices (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    fetched_at      TEXT    NOT NULL,       -- ISO 8601 timestamp of when we fetched
    quote_time      TEXT,                   -- timestamp from the data (e.g., "09:16:14")
    quote_date      TEXT,                   -- date from the data     (e.g., "2026-06-25")
    open_price      REAL,                   -- today's open
    current_price   REAL,                   -- current/last price
    max_today       REAL,                   -- intra-day high
    min_today       REAL,                   -- intra-day low
    raw_response    TEXT,                   -- full raw string for reprocessing
    created_at      TEXT    NOT NULL                -- UTC+8 timestamp
);

CREATE INDEX IF NOT EXISTS idx_fetched_at ON gold_prices(fetched_at DESC);
CREATE INDEX IF NOT EXISTS idx_quote_date ON gold_prices(quote_date, quote_time);

CREATE TABLE IF NOT EXISTS signals (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    recorded_at TEXT    NOT NULL,       -- when the signal was generated (UTC+8 ISO)
    action      TEXT    NOT NULL CHECK(action IN ('BUY', 'SELL', 'HOLD')),
    strength    REAL    NOT NULL DEFAULT 0.0,
    reason      TEXT    NOT NULL DEFAULT '',
    indicator   TEXT    NOT NULL DEFAULT '',  -- e.g. "SMA Crossover", "RSI", "CONSENSUS"
    price       REAL,                   -- gold price at signal time
    bar_time    TEXT,                   -- minute bar timestamp
    created_at  TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_signal_recorded_at ON signals(recorded_at DESC);
