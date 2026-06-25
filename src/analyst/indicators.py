import math


def sma(values: list[float], period: int) -> list[float | None]:
    n = len(values)
    result: list[float | None] = [None] * n
    for i in range(period - 1, n):
        result[i] = sum(values[i - period + 1 : i + 1]) / period
    return result


def ema(values: list[float], period: int) -> list[float]:
    n = len(values)
    alpha = 2.0 / (period + 1)
    result: list[float] = [0.0] * n

    # seed with SMA
    if n >= period:
        result[period - 1] = sum(values[:period]) / period
    else:
        result[0] = values[0]
        for i in range(1, n):
            result[i] = alpha * values[i] + (1 - alpha) * result[i - 1]
        return result

    for i in range(period, n):
        result[i] = alpha * values[i] + (1 - alpha) * result[i - 1]

    return result


def rsi(
    values: list[float], period: int = 14
) -> tuple[list[float | None], float | None, float | None]:
    n = len(values)
    result: list[float | None] = [None] * n
    if n < period + 1:
        return result, None, None

    gains: list[float] = []
    losses: list[float] = []
    for i in range(1, n):
        delta = values[i] - values[i - 1]
        gains.append(delta if delta > 0 else 0.0)
        losses.append(-delta if delta < 0 else 0.0)

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(gains)):
        idx = i + 1  # gains[i] is diff between values[i] and values[i+1]; RSI result at i+1
        if avg_loss == 0:
            result[idx] = 100.0
        else:
            rs = avg_gain / avg_loss
            result[idx] = 100.0 - 100.0 / (1.0 + rs)

        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    return result, avg_gain, avg_loss


def bollinger_bands(
    values: list[float], period: int = 20, k: float = 2.0
) -> dict[str, list[float | None]]:
    n = len(values)
    upper: list[float | None] = [None] * n
    middle: list[float | None] = [None] * n
    lower: list[float | None] = [None] * n

    for i in range(period - 1, n):
        window = values[i - period + 1 : i + 1]
        m = sum(window) / period
        variance = sum((x - m) ** 2 for x in window) / period
        std = math.sqrt(variance)
        middle[i] = m
        upper[i] = m + k * std
        lower[i] = m - k * std

    return {"upper": upper, "middle": middle, "lower": lower}


def macd(
    values: list[float],
) -> tuple[list[float | None], list[float | None], list[float | None]]:
    ema12 = ema(values, 12)
    ema26 = ema(values, 26)

    n = len(values)
    macd_line: list[float | None] = [None] * n
    # MACD line only meaningful from index 25 (where both EMA12 and EMA26
    # have SMA-seeded values); earlier indices are seeded with SMA which is
    # too unstable for meaningful MACD computation.
    ema12_arr = list(ema12)  # type: ignore[arg-type]
    ema26_arr = list(ema26)  # type: ignore[arg-type]
    for i in range(25, n):
        macd_line[i] = ema12_arr[i] - ema26_arr[i]

    valid_indices = [i for i in range(n) if macd_line[i] is not None]
    valid_values = [macd_line[i] for i in valid_indices]  # type: ignore[misc]

    if len(valid_values) < 9:
        signal_line: list[float | None] = [None] * n
        histogram: list[float | None] = [None] * n
        return macd_line, signal_line, histogram

    ema_signal_raw = ema(valid_values, 9)
    signal_line = [None] * n
    histogram = [None] * n
    for i, vi in enumerate(valid_indices):
        signal_line[vi] = ema_signal_raw[i]
        if macd_line[vi] is not None and signal_line[vi] is not None:
            histogram[vi] = macd_line[vi] - signal_line[vi]

    return macd_line, signal_line, histogram
