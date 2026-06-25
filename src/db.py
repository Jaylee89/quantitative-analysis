import sqlite3
from pathlib import Path
from typing import Optional

_DB_PATH: Optional[Path] = None


def _get_db_path() -> Path:
    if _DB_PATH is None:
        raise RuntimeError("DB path not set. Call init_db(path) first.")
    return _DB_PATH


def get_connection() -> sqlite3.Connection:
    db_path = _get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.row_factory = sqlite3.Row
    return conn


def init_db(path: Path) -> None:
    global _DB_PATH
    _DB_PATH = path

    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS gold_prices (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            fetched_at      TEXT    NOT NULL,
            quote_time      TEXT,
            quote_date      TEXT,
            open_price      REAL,
            current_price   REAL,
            max_today       REAL,
            min_today       REAL,
            raw_response    TEXT,
            created_at      TEXT    NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_fetched_at ON gold_prices(fetched_at DESC);
        CREATE INDEX IF NOT EXISTS idx_quote_date ON gold_prices(quote_date, quote_time);
    """)
    conn.commit()
    conn.close()


def insert_record(fetched_at: str, parsed: dict, raw_response: str, created_at: str) -> None:
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO gold_prices
            (fetched_at, quote_date, quote_time, open_price, current_price,
             max_today, min_today, raw_response, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            fetched_at,
            parsed.get("quote_date"),
            parsed.get("quote_time"),
            parsed.get("open_price"),
            parsed.get("current_price"),
            parsed.get("max_today"),
            parsed.get("min_today"),
            raw_response,
            created_at,
        ),
    )
    conn.commit()
    conn.close()
