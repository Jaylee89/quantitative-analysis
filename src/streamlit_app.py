"""
Streamlit dashboard for gold price signals.

Usage:
    streamlit run src/streamlit_app.py
"""

import time
from pathlib import Path

import altair as alt
import streamlit as st
import pandas as pd

from .analyst.engine import SignalEngine
from .analyst.indicators import sma, rsi, bollinger_bands

DB_PATH = Path("data/gold.db")


@st.cache_resource
def _get_engine() -> SignalEngine:
    if not DB_PATH.exists():
        st.error(f"Database not found: {DB_PATH}. Start the collector first.")
        st.stop()
    return SignalEngine(DB_PATH)


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

    df["t"] = df["dt"].dt.strftime("%H:%M")

    line_price = (
        alt.Chart(df)
        .mark_line(color="#2196F3", strokeWidth=2)
        .encode(
            x=alt.X("t:T", title="Time"),
            y=alt.Y("close:Q", title="Price", scale=alt.Scale(zero=False)),
            tooltip=["t", alt.Tooltip("close:Q", format=".2f")],
        )
    )

    line_sma5 = (
        alt.Chart(df)
        .mark_line(color="#FF9800", strokeWidth=1, opacity=0.8)
        .encode(x="t:T", y=alt.Y("sma5:Q", title="Price"))
    )

    line_sma20 = (
        alt.Chart(df)
        .mark_line(color="#9C27B0", strokeWidth=1, opacity=0.8)
        .encode(x="t:T", y=alt.Y("sma20:Q"))
    )

    bb_area = (
        alt.Chart(df)
        .mark_area(opacity=0.08, color="#4CAF50")
        .encode(x="t:T", y="bb_upper:Q", y2="bb_lower:Q")
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

    df["t"] = df["dt"].dt.strftime("%H:%M")

    line = (
        alt.Chart(df)
        .mark_line(color="#E91E63", strokeWidth=2)
        .encode(x="t:T", y=alt.Y("rsi:Q", scale=alt.Scale(domain=[0, 100])))
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


def main() -> None:
    st.set_page_config(page_title="Gold Signal Dashboard", layout="wide")
    st.title("Gold Quantitative Signal Dashboard")

    engine = _get_engine()

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
            st.altair_chart(chart, use_container_width=True)
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
            st.altair_chart(rsi_chart, use_container_width=True)
        else:
            st.info("Not enough data for RSI.")

    with col4:
        macd_chart = _build_macd_chart(snapshot)
        if macd_chart is not None:
            st.altair_chart(macd_chart, use_container_width=True)
        else:
            st.info("Not enough data for MACD.")

    st.divider()
    st.subheader("Signal History")
    signal_log = engine.get_signal_log()
    if signal_log:
        st.dataframe(pd.DataFrame(signal_log), use_container_width=True, hide_index=True)
    else:
        st.info("No signals triggered yet.")

    time.sleep(2)
    st.rerun()


if __name__ == "__main__":
    main()
