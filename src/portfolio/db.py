import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from .models import PortfolioData, BuyRecord

_TZ_UTC8 = timedelta(hours=8)

_PORTFOLIO_DB_PATH: Optional[Path] = None


def _get_conn(timeout: float = 5.0) -> sqlite3.Connection:
    if _PORTFOLIO_DB_PATH is None:
        raise RuntimeError("Portfolio DB path not set. Call init_db(path) first.")
    path = _PORTFOLIO_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=timeout)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(path: Path) -> None:
    global _PORTFOLIO_DB_PATH
    _PORTFOLIO_DB_PATH = path

    conn = _get_conn()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS portfolio (
                id                  INTEGER PRIMARY KEY CHECK(id = 1),
                total_grams         REAL    NOT NULL,
                total_cost          REAL    NOT NULL,
                avg_cost_per_gram   REAL    NOT NULL,
                updated_at          TEXT    NOT NULL,
                created_at          TEXT    NOT NULL
            );

            CREATE TABLE IF NOT EXISTS buy_records (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                grams           REAL    NOT NULL,
                price_per_gram  REAL    NOT NULL,
                total_amount    REAL    NOT NULL,
                bought_at       TEXT    NOT NULL,
                created_at      TEXT    NOT NULL
            );
        """)
        conn.commit()
    finally:
        conn.close()


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone(timezone(_TZ_UTC8)).isoformat(timespec="seconds")


def get_portfolio() -> Optional[PortfolioData]:
    conn = _get_conn()
    try:
        row = conn.execute("SELECT * FROM portfolio WHERE id = 1").fetchone()
        if row is None:
            return None
        return PortfolioData(
            total_grams=row["total_grams"],
            total_cost=row["total_cost"],
            avg_cost_per_gram=row["avg_cost_per_gram"],
            updated_at=row["updated_at"],
        )
    finally:
        conn.close()


def save_portfolio(total_grams: float, total_cost: float) -> PortfolioData:
    avg_cost = total_cost / total_grams if total_grams > 0 else 0.0
    now = _now_iso()

    conn = _get_conn()
    try:
        conn.execute(
            """
            INSERT OR REPLACE INTO portfolio (id, total_grams, total_cost, avg_cost_per_gram, updated_at, created_at)
            VALUES (1, ?, ?, ?, ?,
                COALESCE((SELECT created_at FROM portfolio WHERE id = 1), ?))
            """,
            (total_grams, total_cost, avg_cost, now, now),
        )
        conn.commit()
    finally:
        conn.close()

    return PortfolioData(
        total_grams=total_grams,
        total_cost=total_cost,
        avg_cost_per_gram=avg_cost,
        updated_at=now,
    )


def add_buy_record(grams: float, price_per_gram: float) -> PortfolioData:
    total_amount = grams * price_per_gram
    now = _now_iso()

    conn = _get_conn()
    try:
        # Read current portfolio inside same transaction
        row = conn.execute("SELECT * FROM portfolio WHERE id = 1").fetchone()
        if row is None:
            new_grams = grams
            new_cost = total_amount
        else:
            new_grams = row["total_grams"] + grams
            new_cost = row["total_cost"] + total_amount

        new_avg = new_cost / new_grams if new_grams > 0 else 0.0

        conn.execute(
            """
            INSERT OR REPLACE INTO portfolio (id, total_grams, total_cost, avg_cost_per_gram, updated_at, created_at)
            VALUES (1, ?, ?, ?, ?,
                COALESCE((SELECT created_at FROM portfolio WHERE id = 1), ?))
            """,
            (new_grams, new_cost, new_avg, now, now),
        )
        conn.execute(
            """
            INSERT INTO buy_records (grams, price_per_gram, total_amount, bought_at, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (grams, price_per_gram, total_amount, now, now),
        )
        conn.commit()
    finally:
        conn.close()

    return PortfolioData(
        total_grams=new_grams,
        total_cost=new_cost,
        avg_cost_per_gram=new_avg,
        updated_at=now,
    )


def get_buy_records(limit: int = 50) -> list[BuyRecord]:
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM buy_records ORDER BY bought_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [
            BuyRecord(
                id=r["id"],
                grams=r["grams"],
                price_per_gram=r["price_per_gram"],
                total_amount=r["total_amount"],
                bought_at=r["bought_at"],
            )
            for r in rows
        ]
    finally:
        conn.close()


def delete_buy_record(record_id: int) -> Optional[PortfolioData]:
    conn = _get_conn()
    try:
        row = conn.execute("SELECT * FROM buy_records WHERE id = ?", (record_id,)).fetchone()
        if row is None:
            return None

        removed_grams = row["grams"]
        removed_amount = row["total_amount"]

        conn.execute("DELETE FROM buy_records WHERE id = ?", (record_id,))

        cur = conn.execute("SELECT * FROM portfolio WHERE id = 1")
        portfolio_row = cur.fetchone()
        if portfolio_row is None:
            conn.commit()
            return None

        new_grams = portfolio_row["total_grams"] - removed_grams
        new_cost = portfolio_row["total_cost"] - removed_amount
        now = _now_iso()

        if new_grams <= 0 or new_cost <= 0:
            conn.execute("DELETE FROM portfolio WHERE id = 1")
            conn.commit()
            return None

        new_avg = new_cost / new_grams
        conn.execute(
            """
            INSERT OR REPLACE INTO portfolio (id, total_grams, total_cost, avg_cost_per_gram, updated_at, created_at)
            VALUES (1, ?, ?, ?, ?,
                COALESCE((SELECT created_at FROM portfolio WHERE id = 1), ?))
            """,
            (new_grams, new_cost, new_avg, now, now),
        )
        conn.commit()

        return PortfolioData(
            total_grams=new_grams,
            total_cost=new_cost,
            avg_cost_per_gram=new_avg,
            updated_at=now,
        )
    finally:
        conn.close()
