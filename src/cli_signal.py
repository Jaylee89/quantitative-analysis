"""
Terminal-based gold price signal monitor.

Usage:
    python -m src.cli_signal [--db data/gold.db] [--interval 2]

Displays a live-updating table with technical indicators and buy/sell signals.
"""

import argparse
import time
from pathlib import Path

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.table import Table
from rich.text import Text

from .analyst.engine import SignalEngine
from .portfolio import (
    init_db as init_portfolio_db,
    get_portfolio,
    calc_portfolio_snapshot,
    calc_buy_suggestion,
    calc_sell_suggestion,
)
from .portfolio.engine import set_gold_db_path

PORTFOLIO_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "portfolio.db"


def build_table(snapshot: dict) -> Table:
    bars = snapshot.get("bars", [])
    indicators = snapshot.get("indicators", {})
    signals = snapshot.get("signals", [])
    consensus = snapshot.get("consensus", "HOLD")
    consensus_strength = snapshot.get("consensus_strength", 0.0)

    # Price detail table (last 20 bars)
    table = Table(title=f"Gold Signal Monitor — {snapshot.get('last_updated', '')}")
    table.add_column("Time", style="cyan", no_wrap=True)
    table.add_column("Price", justify="right", style="white")
    table.add_column("SMA(5)", justify="right", style="yellow")
    table.add_column("SMA(20)", justify="right", style="dim")
    table.add_column("RSI(14)", justify="right", style="magenta")
    table.add_column("%B", justify="right", style="blue")
    table.add_column("MACD", justify="right", style="green")
    table.add_column("Signal", justify="center", no_wrap=True)

    # Show last 20 bars
    display_bars = bars[-20:] if len(bars) > 20 else bars
    for bar in display_bars:
        req_idx = bars.index(bar)

        time_str = bar["dt"].strftime("%H:%M")
        price_str = f"{bar['close']:.2f}"

        sma5_val = indicators.get("sma_5")
        sma20_val = indicators.get("sma_20")
        rsi_val = indicators.get("rsi_14")
        bb_upper = indicators.get("bb_upper")
        bb_lower = indicators.get("bb_lower")
        macd_val = indicators.get("macd")
        bb_mid = indicators.get("bb_middle")

        sma5_s = f"{sma5_val:.2f}" if sma5_val is not None else "—"
        sma20_s = f"{sma20_val:.2f}" if sma20_val is not None else "—"
        rsi_s = f"{rsi_val:.1f}" if rsi_val is not None else "—"
        pct_b_s = "—"
        if bb_upper is not None and bb_lower is not None and bb_mid is not None:
            bw = bb_upper - bb_lower
            if bw > 0:
                pct_b = (bar["close"] - bb_lower) / bw
                pct_b_s = f"{pct_b:.2f}"
        macd_s = f"{macd_val:+.4f}" if macd_val is not None else "—"

        signal_text = _bar_signal(req_idx, signals, bars)

        table.add_row(time_str, price_str, sma5_s, sma20_s, rsi_s, pct_b_s, macd_s, signal_text)

    return table


def _bar_signal(idx: int, signals: list[dict], bars: list) -> str:
    """Return signal indicator for a specific bar index."""
    if idx != len(bars) - 1:
        return "·"
    buy_count = sum(1 for s in signals if s["action"] == "BUY")
    sell_count = sum(1 for s in signals if s["action"] == "SELL")
    if buy_count > sell_count:
        return "[green]BUY[/]"
    elif sell_count > buy_count:
        return "[red]SELL[/]"
    return "[dim]—[/]"


def build_footer(snapshot: dict) -> Table:
    consensus = snapshot.get("consensus", "HOLD")
    strength = snapshot.get("consensus_strength", 0.0)
    buy_n = snapshot.get("buy_signals", 0)
    sell_n = snapshot.get("sell_signals", 0)
    signals = snapshot.get("signals", [])
    latest_price = snapshot.get("latest_price")

    style_map = {"BUY": "green", "SELL": "red", "HOLD": "yellow"}
    consensus_text = Text(
        f"Consensus: {consensus} (strength {strength:.2f})",
        style=style_map.get(consensus, "white"),
    )

    t = Table.grid(padding=(0, 1))
    t.add_row(consensus_text)
    t.add_row(Text(f"BUY signals: {buy_n}  SELL signals: {sell_n}", style="dim"))
    for s in signals:
        if s["action"] != "HOLD":
            t.add_row(Text(f"  {s['reason']} ({s['strength']:.2f})", style="dim"))

    # Portfolio summary
    t.add_row(Text(""))
    portfolio = get_portfolio()
    if portfolio is not None and latest_price is not None:
        snap = calc_portfolio_snapshot(portfolio, latest_price)
        pnl_style = "green" if snap["pnl"] >= 0 else "red"
        t.add_row(Text(
            f"Portfolio: {portfolio.total_grams:.2f}g  |  "
            f"Avg Cost: {portfolio.avg_cost_per_gram:.2f}  |  "
            f"Current: {latest_price:.2f}",
            style="bold",
        ))
        t.add_row(Text(
            f"Value: {snap['current_value']:.2f}  |  "
            f"PnL: {snap['pnl']:+.2f} ({snap['pnl_percent']:+.2f}%)",
            style=pnl_style,
        ))

        buy_suggestion = calc_buy_suggestion(portfolio, latest_price)
        if buy_suggestion is not None:
            t.add_row(Text(
                f"建议买入 {buy_suggestion['grams_needed']:.2f}g"
                f" (~{buy_suggestion['amount_needed']:.2f}¥)"
                f" 降至 {buy_suggestion['target_avg_price']:.2f}/g",
                style="cyan",
            ))
        else:
            sell_suggestion = calc_sell_suggestion(portfolio, latest_price)
            if sell_suggestion is not None:
                t.add_row(Text(
                    f"全部卖出可盈利 {sell_suggestion['profit']:+.2f}¥"
                    f" (+{sell_suggestion['profit_percent']:.2f}%)",
                    style="green",
                ))

    return t


def build_layout(snapshot: dict) -> Layout:
    layout = Layout()
    layout.split_column(
        Layout(build_table(snapshot), name="main"),
        Layout(build_footer(snapshot), name="footer", size=12),
    )
    return layout


def main() -> None:
    parser = argparse.ArgumentParser(description="Gold Price Signal Monitor")
    parser.add_argument("--db", default="data/gold.db", help="Path to SQLite database")
    parser.add_argument("--signals-db", default="data/signals.db", help="Path to signals SQLite database")
    parser.add_argument("--interval", type=float, default=2.0, help="Poll interval (seconds)")
    args = parser.parse_args()

    db_path = Path(args.db)
    signals_db_path = Path(args.signals_db)
    if not db_path.exists():
        print(f"Database not found: {db_path}")
        print("Start the collector first with: python -m src.collector")
        return

    # Init portfolio
    init_portfolio_db(PORTFOLIO_DB_PATH)
    set_gold_db_path(db_path)

    engine = SignalEngine(db_path, signals_db_path=signals_db_path)
    console = Console()

    try:
        # Initial full load
        with console.status("Loading historical data..."):
            snapshot = engine.refresh()
        bar_count = snapshot.get("bar_count", 0)
        console.print(f"[dim]Loaded {bar_count} minute bars from database.[/]")
        time.sleep(0.5)

        with Live(refresh_per_second=4, screen=True) as live:
            while True:
                result = engine.tick()
                if result is not None:
                    snapshot = result
                live.update(build_layout(snapshot))
                time.sleep(args.interval)
    except KeyboardInterrupt:
        console.print("\n[dim]Signal monitor stopped.[/]")


if __name__ == "__main__":
    main()
