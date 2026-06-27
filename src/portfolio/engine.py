from pathlib import Path
from typing import Optional

from .models import PortfolioData

_GOLD_DB_PATH: Optional[Path] = None


def set_gold_db_path(path: Path) -> None:
    global _GOLD_DB_PATH
    _GOLD_DB_PATH = path


def get_latest_price() -> Optional[float]:
    """Fetch the latest current_price from gold_prices table."""
    if _GOLD_DB_PATH is None:
        return None
    import sqlite3
    conn = sqlite3.connect(str(_GOLD_DB_PATH))
    try:
        row = conn.execute(
            "SELECT current_price FROM gold_prices WHERE current_price IS NOT NULL ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def calc_portfolio_snapshot(
    portfolio: PortfolioData,
    current_price: float,
) -> dict:
    current_value = portfolio.total_grams * current_price
    pnl = current_value - portfolio.total_cost
    pnl_percent = (pnl / portfolio.total_cost * 100) if portfolio.total_cost > 0 else 0.0
    return {
        "current_value": round(current_value, 2),
        "pnl": round(pnl, 2),
        "pnl_percent": round(pnl_percent, 2),
        "break_even_price": round(portfolio.avg_cost_per_gram, 2),
    }


def calc_buy_suggestion(
    portfolio: PortfolioData,
    current_price: float,
) -> Optional[dict]:
    """Suggest buying to lower average cost.

    Target avg price = current_price * 1.01 (1% above current price).
    Returns None if current_price >= avg_cost_per_gram (no need to average down).
    """
    if current_price >= portfolio.avg_cost_per_gram:
        return None

    target_price = round(current_price * 1.01, 2)

    # Formula: grams_needed = (total_cost - target_price * total_grams) / (target_price - current_price)
    numerator = portfolio.total_cost - target_price * portfolio.total_grams
    denominator = target_price - current_price

    if denominator <= 0 or numerator <= 0:
        return None

    grams_needed = numerator / denominator
    amount_needed = grams_needed * current_price

    return {
        "target_avg_price": target_price,
        "grams_needed": round(grams_needed, 2),
        "amount_needed": round(amount_needed, 2),
    }


def calc_sell_suggestion(
    portfolio: PortfolioData,
    current_price: float,
) -> Optional[dict]:
    """Suggest selling all holdings for profit.

    Returns None if current_price <= avg_cost_per_gram (no profit).
    """
    if current_price <= portfolio.avg_cost_per_gram:
        return None

    profit = portfolio.total_grams * (current_price - portfolio.avg_cost_per_gram)
    profit_percent = ((current_price - portfolio.avg_cost_per_gram) / portfolio.avg_cost_per_gram) * 100

    return {
        "profit": round(profit, 2),
        "profit_percent": round(profit_percent, 2),
        "total_value": round(portfolio.total_grams * current_price, 2),
    }
