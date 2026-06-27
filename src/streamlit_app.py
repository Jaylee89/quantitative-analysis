"""
Streamlit dashboard for gold price signals + portfolio management.

Usage:
    PYTHONPATH=. streamlit run src/streamlit_app.py
"""

import time
from pathlib import Path

import altair as alt
import streamlit as st
import pandas as pd

from src.analyst.engine import SignalEngine
from src.analyst.indicators import sma, rsi, bollinger_bands
from src.portfolio import (
    init_db as init_portfolio_db,
    get_portfolio,
    save_portfolio,
    add_buy_record,
    get_buy_records,
    delete_buy_record,
    calc_portfolio_snapshot,
    calc_buy_suggestion,
    calc_sell_suggestion,
    get_latest_price,
)
from src.portfolio.engine import set_gold_db_path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "gold.db"
SIGNALS_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "signals.db"
PORTFOLIO_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "portfolio.db"

# Init portfolio DB
init_portfolio_db(PORTFOLIO_DB_PATH)
set_gold_db_path(DB_PATH)


@st.cache_resource
def _get_engine() -> SignalEngine:
    if not DB_PATH.exists():
        st.error(f"Database not found: {DB_PATH}. Start the collector first.")
        st.stop()
    return SignalEngine(DB_PATH, signals_db_path=SIGNALS_DB_PATH)


def _enrich_bars(bars: list[dict]) -> pd.DataFrame:
    """Compute indicator line values per bar and return a DataFrame."""
    if not bars:
        return pd.DataFrame()

    df = pd.DataFrame(bars)
    closes = [b["close"] for b in bars]

    df["sma5"] = _pad(sma(closes, 5))
    df["sma20"] = _pad(sma(closes, 20))
    rsi_vals, _, _ = rsi(closes, 14)
    df["rsi"] = _pad(rsi_vals)
    bb = bollinger_bands(closes, 20, 2.0)
    df["bb_upper"] = _pad(bb["upper"])
    df["bb_middle"] = _pad(bb["middle"])
    df["bb_lower"] = _pad(bb["lower"])

    return df


def _pad(arr: list) -> list:
    """Replace None with NaN for Altair."""
    return [v if v is not None else float("nan") for v in arr]


def _build_price_chart(df: pd.DataFrame) -> alt.Chart | None:
    if df.empty:
        return None

    line_price = (
        alt.Chart(df)
        .mark_line(color="#2196F3", strokeWidth=2)
        .encode(
            x=alt.X("dt:T", title="Time", axis=alt.Axis(format="%H:%M")),
            y=alt.Y("close:Q", title="Price", scale=alt.Scale(zero=False)),
            tooltip=[alt.Tooltip("dt:T", format="%H:%M"), alt.Tooltip("close:Q", format=".2f")],
        )
    )

    line_sma5 = (
        alt.Chart(df)
        .mark_line(color="#FF9800", strokeWidth=1, opacity=0.8)
        .encode(x="dt:T", y=alt.Y("sma5:Q", title="Price"))
    )

    line_sma20 = (
        alt.Chart(df)
        .mark_line(color="#9C27B0", strokeWidth=1, opacity=0.8)
        .encode(x="dt:T", y=alt.Y("sma20:Q"))
    )

    bb_area = (
        alt.Chart(df)
        .mark_area(opacity=0.08, color="#4CAF50")
        .encode(x="dt:T", y="bb_upper:Q", y2="bb_lower:Q")
    )

    chart = (
        alt.layer(bb_area, line_price, line_sma5, line_sma20)
        .properties(height=380, title="Gold Price — SMA(5/20) + Bollinger Bands")
        .interactive()
    )
    return chart


def _build_rsi_chart(df: pd.DataFrame) -> alt.Chart | None:
    if df.empty:
        return None
    df = df.dropna(subset=["rsi"]).copy()
    if df.empty:
        return None

    line = (
        alt.Chart(df)
        .mark_line(color="#E91E63", strokeWidth=2)
        .encode(x="dt:T", y=alt.Y("rsi:Q", scale=alt.Scale(domain=[0, 100])))
    )

    overbought = (
        alt.Chart(pd.DataFrame({"y": [70]}))
        .mark_rule(strokeDash=[4, 4], color="red", opacity=0.4)
        .encode(y="y:Q")
    )

    oversold = (
        alt.Chart(pd.DataFrame({"y": [30]}))
        .mark_rule(strokeDash=[4, 4], color="green", opacity=0.4)
        .encode(y="y:Q")
    )

    return (
        (line + overbought + oversold)
        .properties(height=180, title="RSI(14)")
        .interactive()
    )


def _build_macd_chart(snapshot: dict) -> alt.Chart | None:
    ind = snapshot.get("indicators", {})
    macd_val = ind.get("macd")
    macd_sig = ind.get("macd_signal")
    macd_hist = ind.get("macd_histogram")

    if macd_val is None:
        return None

    rows = []
    rows.append({"label": "MACD", "value": macd_val, "type": "line"})
    if macd_sig is not None:
        rows.append({"label": "Signal", "value": macd_sig, "type": "line"})
    if macd_hist is not None:
        rows.append({"label": "Histogram", "value": macd_hist, "type": "bar"})

    chart_df = pd.DataFrame(rows)

    bars = (
        alt.Chart(chart_df.query("type == 'bar'"))
        .mark_bar(thickness=15, opacity=0.7)
        .encode(
            x=alt.X("label:N", title="", axis=alt.Axis(labels=False), sort=None),
            y=alt.Y("value:Q"),
            color=alt.condition(
                alt.datum.value >= 0,
                alt.value("#4CAF50"),
                alt.value("#F44336"),
            ),
            tooltip=alt.Tooltip("value:Q", format=".4f"),
        )
    )

    dots = (
        alt.Chart(chart_df.query("type == 'line'"))
        .mark_circle(size=80, opacity=0.8)
        .encode(
            x=alt.X("label:N", sort=None),
            y="value:Q",
            color=alt.Color("label:N", legend=None, scale=alt.Scale(
                domain=["MACD", "Signal"],
                range=["#2196F3", "#FF9800"],
            )),
            tooltip=alt.Tooltip("value:Q", format=".4f"),
        )
    )

    chart = alt.layer(bars, dots).properties(height=180, title="MACD")
    return chart


def _render_signal_dashboard(engine: SignalEngine) -> None:
    snapshot = engine.tick()
    if snapshot is None:
        snapshot = engine.refresh()

    if snapshot.get("bar_count", 0) == 0:
        st.warning("No data available yet.")
        time.sleep(2)
        st.rerun()

    bars = snapshot.get("bars", [])
    df = _enrich_bars(bars)

    col1, col2 = st.columns([3, 1])

    with col1:
        chart = _build_price_chart(df)
        if chart is not None:
            st.altair_chart(chart, width='stretch')
        else:
            st.info("Not enough data for price chart.")

    with col2:
        latest = snapshot.get("latest_price")
        consensus = snapshot.get("consensus", "HOLD")
        strength = snapshot.get("consensus_strength", 0.0)
        buy_n = snapshot.get("buy_signals", 0)
        sell_n = snapshot.get("sell_signals", 0)
        bar_count = snapshot.get("bar_count", 0)
        last_updated = snapshot.get("last_updated", "")

        if latest is not None:
            st.metric("Current Price", f"{latest:.4f}")

        cmap = {"BUY": "green", "SELL": "red", "HOLD": "gray"}
        st.markdown(
            f"### Consensus: :{cmap.get(consensus, 'gray')}[{consensus}] "
            f"(strength {strength:.2f})"
        )
        st.markdown(f"**BUY:** {buy_n}  **SELL:** {sell_n}")
        st.markdown(f"**Bars:** {bar_count}")
        st.caption(f"Updated: {last_updated}")

        st.divider()
        st.subheader("Active Signals")
        for sig in snapshot.get("signals", []):
            if sig["action"] != "HOLD":
                color = cmap.get(sig["action"], "gray")
                st.markdown(
                    f"- :{color}[{sig['action']}] {sig['reason']} ({sig['strength']:.2f})"
                )

        st.divider()
        st.subheader("Indicators")
        ind = snapshot.get("indicators", {})
        for key in ["sma_5", "sma_20", "rsi_14", "bb_upper", "bb_lower", "macd", "macd_signal", "macd_histogram"]:
            val = ind.get(key)
            if val is not None:
                st.markdown(f"**{key}:** {val:.4f}")

    col3, col4 = st.columns(2)
    with col3:
        rsi_chart = _build_rsi_chart(df)
        if rsi_chart is not None:
            st.altair_chart(rsi_chart, width='stretch')
        else:
            st.info("Not enough data for RSI.")

    with col4:
        macd_chart = _build_macd_chart(snapshot)
        if macd_chart is not None:
            st.altair_chart(macd_chart, width='stretch')
        else:
            st.info("Not enough data for MACD.")

    st.divider()
    st.subheader("Signal History")
    signal_log = engine.get_signal_log()
    if signal_log:
        st.dataframe(pd.DataFrame(signal_log), width='stretch', hide_index=True)
    else:
        st.info("No signals triggered yet.")


def _render_portfolio_page() -> None:
    st.subheader("Portfolio Management")

    current_price = get_latest_price()
    portfolio = get_portfolio()

    # Display current price info
    if current_price is not None:
        st.metric("Current Gold Price", f"{current_price:.2f} /g")
    else:
        st.info("No price data available. Start the collector first.")

    st.divider()

    # ── Portfolio Overview ──
    if portfolio is not None and current_price is not None:
        snap = calc_portfolio_snapshot(portfolio, current_price)

        col1, col2, col3, col4, col5 = st.columns(5)
        col1.metric("Total Grams", f"{portfolio.total_grams:.4f} g")
        col2.metric("Avg Cost /g", f"{portfolio.avg_cost_per_gram:.2f}")
        col3.metric("Total Cost", f"{portfolio.total_cost:.2f}")
        delta_color = "inverse" if snap["pnl"] < 0 else "normal"
        col4.metric("Current Value", f"{snap['current_value']:.2f}")
        col5.metric("PnL", f"{snap['pnl']:.2f} ({snap['pnl_percent']:+.2f}%)", delta_color=delta_color)

        # ── Suggestion Section ──
        st.divider()
        st.subheader("Suggestion")

        buy_suggestion = calc_buy_suggestion(portfolio, current_price)
        sell_suggestion = calc_sell_suggestion(portfolio, current_price)

        if buy_suggestion is not None:
            st.info(
                f"Current price ({current_price:.2f}) is below your average cost "
                f"({portfolio.avg_cost_per_gram:.2f}). "
                f"建议买入 **{buy_suggestion['grams_needed']:.2f} 克** "
                f"（约 **{buy_suggestion['amount_needed']:.2f} 元**），"
                f"均价可降至 **{buy_suggestion['target_avg_price']:.2f} 元/克**。"
            )
        elif sell_suggestion is not None:
            st.success(
                f"Current price ({current_price:.2f}) is above your average cost "
                f"({portfolio.avg_cost_per_gram:.2f}). "
                f"全部卖出可盈利 **{sell_suggestion['profit']:.2f} 元** "
                f"（+{sell_suggestion['profit_percent']:.2f}%），"
                f"总价值 **{sell_suggestion['total_value']:.2f} 元**。"
            )
        else:
            st.info("当前价格接近成本均价，建议观望等待明确信号。")

    elif portfolio is None:
        st.info("No portfolio data yet. Set up your holdings below.")

    st.divider()

    # ── Set / Edit Portfolio ──
    st.subheader("Set / Edit Portfolio")

    default_grams = portfolio.total_grams if portfolio else 0.0
    default_cost = portfolio.total_cost if portfolio else 0.0

    with st.form("portfolio_form", clear_on_submit=False):
        col1, col2 = st.columns(2)
        with col1:
            grams = st.number_input(
                "Total Grams (g)", min_value=0.0, value=default_grams, step=0.01, format="%.4f"
            )
        with col2:
            cost = st.number_input(
                "Total Cost (¥)", min_value=0.0, value=default_cost, step=0.01, format="%.2f"
            )

        if st.form_submit_button("Save Portfolio", type="primary"):
            if grams > 0 and cost > 0:
                save_portfolio(grams, cost)
                st.success("Portfolio saved!")
                st.rerun()
            else:
                st.error("Grams and cost must be greater than 0.")

    st.divider()

    # ── Record Buy ──
    st.subheader("Record New Buy")

    with st.form("buy_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            buy_grams = st.number_input(
                "Buy Grams (g)", min_value=0.0, step=0.01, format="%.4f"
            )
        with col2:
            buy_price = st.number_input(
                "Price per Gram (¥)", min_value=0.0, step=0.01, format="%.2f"
            )

        if st.form_submit_button("Record Buy", type="primary"):
            if buy_grams > 0 and buy_price > 0:
                new_portfolio = add_buy_record(buy_grams, buy_price)
                st.success(
                    f"Buy recorded! New avg cost: {new_portfolio.avg_cost_per_gram:.2f} /g. "
                    f"Total: {new_portfolio.total_grams:.4f} g"
                )
                st.rerun()
            else:
                st.error("Grams and price must be greater than 0.")

    st.divider()

    # ── Buy History ──
    st.subheader("Buy History")

    records = get_buy_records(limit=50)
    if records:
        df_history = pd.DataFrame(records)
        df_history_display = df_history[["id", "grams", "price_per_gram", "total_amount", "bought_at"]].copy()
        df_history_display.columns = ["ID", "Grams", "Price/g", "Total", "Time"]
        st.dataframe(df_history_display, width='stretch', hide_index=True)

        # Delete a record
        record_ids = [r.id for r in records]
        selected_id = st.selectbox("Delete a buy record (will rollback portfolio)", record_ids)
        if st.button("Delete Selected Record", type="secondary"):
            updated = delete_buy_record(selected_id)
            if updated is not None:
                st.success(
                    f"Record deleted. Portfolio updated: {updated.total_grams:.4f}g, "
                    f"avg cost {updated.avg_cost_per_gram:.2f}/g"
                )
            else:
                st.success("Record deleted and portfolio cleared (no remaining holdings).")
            st.rerun()
    else:
        st.info("No buy records yet.")


def main() -> None:
    st.set_page_config(page_title="Gold Signal Dashboard", layout="wide")
    st.title("Gold Quantitative Signal Dashboard")

    engine = _get_engine()

    tab1, tab2 = st.tabs(["Signal Dashboard", "Portfolio"])

    with tab1:
        _render_signal_dashboard(engine)

    with tab2:
        _render_portfolio_page()

    time.sleep(2)
    st.rerun()


if __name__ == "__main__":
    main()
