from typing import NamedTuple


class SignalResult(NamedTuple):
    action: str  # "BUY" | "SELL" | "HOLD"
    strength: float  # 0.0 (weak) to 1.0 (strong)
    reason: str
    indicator_name: str  # e.g. "SMA Crossover", "RSI"


def evaluate_sma_crossover(
    sma5: list[float | None], sma20: list[float | None]
) -> SignalResult:
    """BUY when SMA5 crosses above SMA20; SELL on cross below."""
    if len(sma5) < 2 or len(sma20) < 2:
        return SignalResult("HOLD", 0.0, "Not enough SMA data", "SMA Crossover")
    if sma5[-2] is None or sma5[-1] is None or sma20[-2] is None or sma20[-1] is None:
        return SignalResult("HOLD", 0.0, "Incomplete SMA values", "SMA Crossover")

    prev_gap = sma5[-2] - sma20[-2]
    curr_gap = sma5[-1] - sma20[-1]

    # Avoid whipsaw: gap change must be > 0.01% of price
    threshold = 0.0001 * abs(sma20[-1])

    if prev_gap <= -threshold and curr_gap >= threshold:
        strength = min(abs(curr_gap) / sma20[-1] * 200, 1.0)  # type: ignore[operator]
        return SignalResult("BUY", strength, "SMA5 crossed above SMA20", "SMA Crossover")
    elif prev_gap >= threshold and curr_gap <= -threshold:
        strength = min(abs(curr_gap) / sma20[-1] * 200, 1.0)  # type: ignore[operator]
        return SignalResult("SELL", strength, "SMA5 crossed below SMA20", "SMA Crossover")

    return SignalResult("HOLD", 0.0, "No crossover", "SMA Crossover")


def evaluate_rsi(rsi_values: list[float | None]) -> SignalResult:
    """BUY when RSI < 30 (oversold); SELL when RSI > 70 (overbought)."""
    if not rsi_values or rsi_values[-1] is None:
        return SignalResult("HOLD", 0.0, "Not enough RSI data", "RSI")

    curr_rsi = rsi_values[-1]
    if curr_rsi < 30:
        strength = min((30 - curr_rsi) / 30, 1.0)
        return SignalResult("BUY", strength, f"RSI {curr_rsi:.1f} < 30 (oversold)", "RSI")
    elif curr_rsi > 70:
        strength = min((curr_rsi - 70) / 30, 1.0)
        return SignalResult("SELL", strength, f"RSI {curr_rsi:.1f} > 70 (overbought)", "RSI")

    # Strong momentum near edges
    if curr_rsi < 35:
        return SignalResult("BUY", 0.3, f"RSI {curr_rsi:.1f} approaching oversold", "RSI")
    elif curr_rsi > 65:
        return SignalResult("SELL", 0.3, f"RSI {curr_rsi:.1f} approaching overbought", "RSI")

    return SignalResult("HOLD", 0.0, f"RSI {curr_rsi:.1f} neutral", "RSI")


def evaluate_bollinger(
    close: list[float],
    bb: dict[str, list[float | None]],
) -> SignalResult:
    """BUY when price touches lower band; SELL when touches upper band."""
    if not close or not bb.get("upper"):
        return SignalResult("HOLD", 0.0, "Not enough BB data", "Bollinger Bands")

    upper = bb["upper"][-1]
    middle = bb["middle"][-1]
    lower = bb["lower"][-1]
    curr_price = close[-1]

    if upper is None or middle is None or lower is None:
        return SignalResult("HOLD", 0.0, "Incomplete BB values", "Bollinger Bands")

    bandwidth = upper - lower
    if bandwidth == 0:
        return SignalResult("HOLD", 0.0, "Zero bandwidth", "Bollinger Bands")

    # %B: where price is within the bands
    percent_b = (curr_price - lower) / bandwidth

    if percent_b <= 0:
        strength = min(abs(percent_b) * 2, 1.0)
        return SignalResult("BUY", strength, f"Price at lower band (%B={percent_b:.2f})", "Bollinger Bands")
    elif percent_b >= 1:
        strength = min((percent_b - 1) * 2, 1.0)
        return SignalResult("SELL", strength, f"Price at upper band (%B={percent_b:.2f})", "Bollinger Bands")

    return SignalResult("HOLD", 0.0, f"%B={percent_b:.2f} within bands", "Bollinger Bands")


def evaluate_macd(
    macd_line: list[float | None],
    signal_line: list[float | None],
) -> SignalResult:
    """BUY when MACD line crosses above signal line; SELL on cross below."""
    # Find last two valid index pairs
    valid_indices = [i for i in range(len(macd_line))
                     if macd_line[i] is not None and signal_line[i] is not None]

    if len(valid_indices) < 2:
        return SignalResult("HOLD", 0.0, "Not enough MACD data", "MACD")

    i2 = valid_indices[-1]
    i1 = valid_indices[-2]

    prev_gap = macd_line[i1] - signal_line[i1]  # type: ignore[operator]
    curr_gap = macd_line[i2] - signal_line[i2]  # type: ignore[operator]

    curr_price = 1.0  # normalized
    threshold = 0.0001 * curr_price

    if prev_gap <= -threshold and curr_gap >= threshold:
        strength = min(abs(curr_gap) * 50, 1.0)
        return SignalResult("BUY", strength, "MACD crossed above signal line", "MACD")
    elif prev_gap >= threshold and curr_gap <= -threshold:
        strength = min(abs(curr_gap) * 50, 1.0)
        return SignalResult("SELL", strength, "MACD crossed below signal line", "MACD")

    return SignalResult("HOLD", 0.0, "No MACD crossover", "MACD")


def evaluate_signals(
    close: list[float],
    sma5: list[float | None],
    sma20: list[float | None],
    rsi_values: list[float | None],
    bb: dict[str, list[float | None]],
    macd_line: list[float | None],
    macd_signal: list[float | None],
) -> list[SignalResult]:
    results: list[SignalResult] = [
        evaluate_sma_crossover(sma5, sma20),
        evaluate_rsi(rsi_values),
        evaluate_bollinger(close, bb),
        evaluate_macd(macd_line, macd_signal),
    ]
    return results


def aggregate_signals(results: list[SignalResult]) -> dict:
    buy_count = sum(1 for r in results if r.action == "BUY")
    sell_count = sum(1 for r in results if r.action == "SELL")
    buy_strength = sum(r.strength for r in results if r.action == "BUY")
    sell_strength = sum(r.strength for r in results if r.action == "SELL")

    if buy_count > sell_count and buy_strength > 0.3:
        consensus = "BUY"
        avg_strength = buy_strength / buy_count if buy_count else 0.0
    elif sell_count > buy_count and sell_strength > 0.3:
        consensus = "SELL"
        avg_strength = sell_strength / sell_count if sell_count else 0.0
    else:
        consensus = "HOLD"
        avg_strength = 0.0

    return {
        "consensus": consensus,
        "avg_strength": round(avg_strength, 2),
        "buy_signals": buy_count,
        "sell_signals": sell_count,
        "total_active": buy_count + sell_count,
    }
