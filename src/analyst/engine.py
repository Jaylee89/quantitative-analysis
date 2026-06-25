import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from .indicators import sma, ema, rsi, bollinger_bands, macd
from .signals import evaluate_signals, aggregate_signals, SignalResult

_TZ_UTC8 = timedelta(hours=8)


def _parse_quote_dt(quote_date: str, quote_time: str) -> datetime:
    """Parse quote_date+quote_time into a timezone-aware datetime (UTC+8)."""
    naive = datetime.strptime(f"{quote_date} {quote_time}", "%Y-%m-%d %H:%M:%S")
    return naive.replace(tzinfo=timezone_utc8())


def timezone_utc8():
    from datetime import timezone
    return timezone(_TZ_UTC8)


def get_connection(db_path: str | Path, timeout: float = 5.0) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), timeout=timeout)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def get_raw_ticks(
    conn: sqlite3.Connection, since_id: int = 0, lookback_minutes: int = 120
) -> list[dict]:
    """Fetch raw tick rows from gold_prices, optionally incremental."""
    if since_id > 0:
        rows = conn.execute(
            """
            SELECT id, quote_date, quote_time, current_price
            FROM gold_prices
            WHERE id > ? AND quote_time IS NOT NULL AND quote_date IS NOT NULL
            ORDER BY id ASC
            """,
            (since_id,),
        ).fetchall()
    else:
        cutoff = (datetime.now(timezone_utc8()) - timedelta(minutes=lookback_minutes)).isoformat()
        rows = conn.execute(
            """
            SELECT id, quote_date, quote_time, current_price
            FROM gold_prices
            WHERE quote_time IS NOT NULL AND quote_date IS NOT NULL
              AND fetched_at >= ?
            ORDER BY id ASC
            """,
            (cutoff,),
        ).fetchall()
    return [dict(r) for r in rows]


def deduplicate_ticks(ticks: list[dict]) -> list[dict]:
    """Keep only the latest tick per (quote_date, quote_time) pair."""
    seen: dict[tuple[str, str], dict] = {}
    for t in ticks:
        key = (t["quote_date"], t["quote_time"])
        seen[key] = t  # later id wins
    return list(seen.values())


def aggregate_minute_bars(ticks: list[dict]) -> list[dict]:
    """Group unique ticks into 1-minute OHLC bars."""
    if not ticks:
        return []

    bars: dict[str, dict] = {}
    for t in ticks:
        dt = _parse_quote_dt(t["quote_date"], t["quote_time"])
        minute_key = dt.strftime("%Y-%m-%d %H:%M")
        price = t["current_price"]

        if minute_key not in bars:
            bars[minute_key] = {
                "dt": dt.replace(second=0, microsecond=0),
                "open": price,
                "high": price,
                "low": price,
                "close": price,
                "volume": 1,
            }
        else:
            bar = bars[minute_key]
            bar["high"] = max(bar["high"], price)
            bar["low"] = min(bar["low"], price)
            bar["close"] = price
            bar["volume"] += 1

    result = sorted(bars.values(), key=lambda b: b["dt"])
    return result


class SignalEngine:
    """Real-time signal engine: DB -> OHLC -> indicators -> signals."""

    def __init__(
        self,
        db_path: str | Path,
        lookback_minutes: int = 120,
    ):
        self._db_path = Path(db_path)
        self._lookback_minutes = lookback_minutes
        self._last_id = 0
        self._bars: list[dict] = []

        # For incremental stats
        self._last_snapshot: dict | None = None
        self._signal_log: list[dict] = []

    def refresh(self) -> dict:
        """Full refresh: reload all available data and recompute."""
        conn = get_connection(self._db_path)
        try:
            ticks = get_raw_ticks(conn, since_id=0, lookback_minutes=self._lookback_minutes)
            unique = deduplicate_ticks(ticks)
            self._bars = aggregate_minute_bars(unique)
            if ticks:
                self._last_id = max(t["id"] for t in ticks)
            return self._build_snapshot()
        finally:
            conn.close()

    def tick(self) -> dict | None:
        """Incremental update: fetch only new rows since last poll.

        Returns None if no new data, otherwise the full snapshot.
        """
        conn = get_connection(self._db_path)
        try:
            new_ticks = get_raw_ticks(conn, since_id=self._last_id)
            if not new_ticks:
                # Nothing new, return previous snapshot or refresh
                if self._last_snapshot is None:
                    return self.refresh()
                return None

            self._last_id = max(t["id"] for t in new_ticks)
            unique = deduplicate_ticks(new_ticks)

            # Extend or rebuild bars
            if unique:
                new_bars = aggregate_minute_bars(unique)
                self._merge_bars(new_bars)

            return self._build_snapshot()
        finally:
            conn.close()

    def get_signal_log(self) -> list[dict]:
        return list(self._signal_log)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _merge_bars(self, new_bars: list[dict]) -> None:
        """Merge new minute bars into the existing bar list, replacing
        the current incomplete minute bar if needed."""
        if not new_bars:
            return

        # Build a lookup of existing bars keyed by minute
        existing = {b["dt"].isoformat(): b for b in self._bars}

        for nb in new_bars:
            key = nb["dt"].isoformat()
            if key in existing:
                # Merge: update existing bar with newer data (current minute)
                existing_bar = existing[key]
                existing_bar["high"] = max(existing_bar["high"], nb["high"])
                existing_bar["low"] = min(existing_bar["low"], nb["low"])
                existing_bar["close"] = nb["close"]  # latest close
                existing_bar["volume"] += nb["volume"]
            else:
                existing[key] = nb

        # Sort and keep
        self._bars = sorted(existing.values(), key=lambda b: b["dt"])

        # Limit to lookback
        if len(self._bars) > self._lookback_minutes:
            self._bars = self._bars[-self._lookback_minutes:]

    def _build_snapshot(self) -> dict:
        bars = self._bars
        if not bars:
            snapshot = {
                "bars": [],
                "indicators": {},
                "signals": [],
                "consensus": "HOLD",
                "latest_price": None,
                "last_updated": datetime.now(timezone_utc8()).isoformat(timespec="seconds"),
                "bar_count": 0,
            }
            self._last_snapshot = snapshot
            return snapshot

        closes = [b["close"] for b in bars]

        # Compute indicators
        sma5 = sma(closes, 5)
        sma20 = sma(closes, 20)
        ema12 = ema(closes, 12)
        ema26 = ema(closes, 26)
        rsi_values, _, _ = rsi(closes, 14)
        bb = bollinger_bands(closes, 20, 2.0)
        macd_line, macd_signal_line, _ = macd(closes)

        # Signals
        signal_results = evaluate_signals(
            closes, sma5, sma20, rsi_values, bb, macd_line, macd_signal_line,
        )
        consensus = aggregate_signals(signal_results)

        # Check for new actionable signals for the log
        for sr in signal_results:
            if sr.action != "HOLD":
                log_entry = {
                    "time": datetime.now(timezone_utc8()).isoformat(timespec="seconds"),
                    "action": sr.action,
                    "reason": sr.reason,
                    "strength": round(sr.strength, 2),
                }
                # Avoid duplicating the exact same signal in the log
                if not self._signal_log or self._signal_log[-1].get("reason") != sr.reason:
                    self._signal_log.append(log_entry)

        # Keep last 50 log entries
        if len(self._signal_log) > 50:
            self._signal_log = self._signal_log[-50:]

        latest_price = bars[-1]["close"]
        indicator_values = {
            "sma_5": _last(sma5),
            "sma_20": _last(sma20),
            "ema_12": _last(ema12),
            "ema_26": _last(ema26),
            "rsi_14": _last(rsi_values),
            "bb_upper": _last(bb["upper"]),
            "bb_middle": _last(bb["middle"]),
            "bb_lower": _last(bb["lower"]),
            "macd": _last(macd_line),
            "macd_signal": _last(macd_signal_line),
            "macd_histogram": (
                (_last(macd_line) - _last(macd_signal_line))
                if _last(macd_line) is not None and _last(macd_signal_line) is not None
                else None
            ),
        }

        snapshot = {
            "bars": bars,
            "indicators": indicator_values,
            "signals": [{
                "action": s.action,
                "strength": round(s.strength, 2),
                "reason": s.reason,
                "indicator": s.indicator_name,
            } for s in signal_results],
            "consensus": consensus["consensus"],
            "consensus_strength": consensus["avg_strength"],
            "buy_signals": consensus["buy_signals"],
            "sell_signals": consensus["sell_signals"],
            "latest_price": latest_price,
            "last_updated": datetime.now(timezone_utc8()).isoformat(timespec="seconds"),
            "bar_count": len(bars),
        }
        self._last_snapshot = snapshot
        return snapshot


def _last(arr: list) -> any:
    """Return last element or None if empty."""
    return arr[-1] if arr else None
