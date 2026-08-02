"""技術指標計算，輸入為單一股票依日期由舊到新排序的收盤/高/低/量序列。

每個函式回傳與輸入等長的 list[float | None]，索引尚不足以計算的位置回傳 None，
避免呼叫端誤把「資料不足」當成「數值為 0」。
"""

from __future__ import annotations


def sma(values: list[float], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    for i in range(period - 1, len(values)):
        window = values[i - period + 1 : i + 1]
        out[i] = sum(window) / period
    return out


def ema(values: list[float], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if len(values) < period:
        return out

    multiplier = 2 / (period + 1)
    seed = sum(values[:period]) / period
    out[period - 1] = seed

    prev = seed
    for i in range(period, len(values)):
        prev = (values[i] - prev) * multiplier + prev
        out[i] = prev
    return out


def rsi(values: list[float], period: int = 14) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if len(values) < period + 1:
        return out

    gains = [0.0]
    losses = [0.0]
    for i in range(1, len(values)):
        change = values[i] - values[i - 1]
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))

    avg_gain = sum(gains[1 : period + 1]) / period
    avg_loss = sum(losses[1 : period + 1]) / period
    out[period] = _rsi_from_averages(avg_gain, avg_loss)

    for i in range(period + 1, len(values)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        out[i] = _rsi_from_averages(avg_gain, avg_loss)

    return out


def _rsi_from_averages(avg_gain: float, avg_loss: float) -> float:
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def macd(
    values: list[float], fast: int = 12, slow: int = 26, signal: int = 9
) -> tuple[list[float | None], list[float | None], list[float | None]]:
    """回傳 (macd_line, signal_line, histogram)。"""
    ema_fast = ema(values, fast)
    ema_slow = ema(values, slow)

    macd_line: list[float | None] = [
        (f - s) if f is not None and s is not None else None
        for f, s in zip(ema_fast, ema_slow)
    ]

    dense = [v for v in macd_line if v is not None]
    signal_dense = ema(dense, signal) if len(dense) >= signal else []

    signal_line: list[float | None] = [None] * len(values)
    first_valid = next((i for i, v in enumerate(macd_line) if v is not None), None)
    if first_valid is not None:
        for offset, sig_val in enumerate(signal_dense):
            if sig_val is not None:
                signal_line[first_valid + offset] = sig_val

    histogram: list[float | None] = [
        (m - s) if m is not None and s is not None else None
        for m, s in zip(macd_line, signal_line)
    ]

    return macd_line, signal_line, histogram


def true_range(high: list[float], low: list[float], close: list[float]) -> list[float | None]:
    out: list[float | None] = [None] * len(close)
    if not close:
        return out
    out[0] = high[0] - low[0]
    for i in range(1, len(close)):
        out[i] = max(
            high[i] - low[i],
            abs(high[i] - close[i - 1]),
            abs(low[i] - close[i - 1]),
        )
    return out


def atr(high: list[float], low: list[float], close: list[float], period: int = 14) -> list[float | None]:
    tr = true_range(high, low, close)
    out: list[float | None] = [None] * len(close)
    if len(close) < period:
        return out

    seed = sum(tr[1 : period + 1]) / period
    out[period] = seed

    prev = seed
    for i in range(period + 1, len(close)):
        prev = (prev * (period - 1) + tr[i]) / period
        out[i] = prev
    return out


def bollinger_bands(
    values: list[float], period: int = 20, num_std: float = 2.0
) -> tuple[list[float | None], list[float | None], list[float | None]]:
    """回傳 (upper, middle, lower)。"""
    middle = sma(values, period)
    upper: list[float | None] = [None] * len(values)
    lower: list[float | None] = [None] * len(values)

    for i in range(period - 1, len(values)):
        window = values[i - period + 1 : i + 1]
        mean = middle[i]
        variance = sum((v - mean) ** 2 for v in window) / period
        std = variance**0.5
        upper[i] = mean + num_std * std
        lower[i] = mean - num_std * std

    return upper, middle, lower


def adx(
    high: list[float], low: list[float], close: list[float], period: int = 14
) -> list[float | None]:
    n = len(close)
    out: list[float | None] = [None] * n
    if n < period * 2:
        return out

    plus_dm = [0.0] * n
    minus_dm = [0.0] * n
    for i in range(1, n):
        up_move = high[i] - high[i - 1]
        down_move = low[i - 1] - low[i]
        if up_move > down_move and up_move > 0:
            plus_dm[i] = up_move
        if down_move > up_move and down_move > 0:
            minus_dm[i] = down_move

    tr = true_range(high, low, close)
    tr[0] = 0.0

    smoothed_tr = sum(tr[1 : period + 1])
    smoothed_plus_dm = sum(plus_dm[1 : period + 1])
    smoothed_minus_dm = sum(minus_dm[1 : period + 1])

    dx_values: list[float | None] = [None] * n

    def _dx(plus_dm_s: float, minus_dm_s: float, tr_s: float) -> float:
        if tr_s == 0:
            return 0.0
        plus_di = 100 * plus_dm_s / tr_s
        minus_di = 100 * minus_dm_s / tr_s
        denom = plus_di + minus_di
        if denom == 0:
            return 0.0
        return 100 * abs(plus_di - minus_di) / denom

    dx_values[period] = _dx(smoothed_plus_dm, smoothed_minus_dm, smoothed_tr)

    for i in range(period + 1, n):
        smoothed_tr = smoothed_tr - (smoothed_tr / period) + tr[i]
        smoothed_plus_dm = smoothed_plus_dm - (smoothed_plus_dm / period) + plus_dm[i]
        smoothed_minus_dm = smoothed_minus_dm - (smoothed_minus_dm / period) + minus_dm[i]
        dx_values[i] = _dx(smoothed_plus_dm, smoothed_minus_dm, smoothed_tr)

    first_dx = period
    last_dx_seed_index = first_dx + period - 1
    if last_dx_seed_index >= n:
        return out

    dx_window = [v for v in dx_values[first_dx : last_dx_seed_index + 1] if v is not None]
    if len(dx_window) < period:
        return out

    adx_val = sum(dx_window) / period
    out[last_dx_seed_index] = adx_val

    for i in range(last_dx_seed_index + 1, n):
        dx_i = dx_values[i]
        if dx_i is None:
            continue
        adx_val = (adx_val * (period - 1) + dx_i) / period
        out[i] = adx_val

    return out
