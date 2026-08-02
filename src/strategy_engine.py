"""策略引擎：讀取 strategy_*.json，對一組股票的價格序列計算指標／衍生因子，
執行 filters 篩選、ranking 排名、entry/exit 訊號判斷。

新增策略只需新增一份 JSON，不需修改本檔案。price series 需含 close，
high/low 為 ATR/ADX 等指標所需時才需要提供。
"""

from __future__ import annotations

from typing import Any

from . import indicators as ind
from .expr import ExpressionError, safe_eval

PriceSeries = dict[str, list[float]]


def compute_indicators(prices: PriceSeries, specs: list[dict[str, Any]]) -> dict[str, list]:
    """依策略 JSON 的 indicators 區塊計算指標序列，key 為指標輸出名稱。"""
    close = prices.get("close", [])
    high = prices.get("high")
    low = prices.get("low")
    results: dict[str, list] = {}

    for spec in specs:
        itype = spec["type"]
        name = spec["name"]
        period = spec.get("period", 14)
        source = prices.get(spec.get("source", "close"), close)

        if itype == "SMA":
            results[name] = ind.sma(source, period)
        elif itype == "EMA":
            results[name] = ind.ema(source, period)
        elif itype == "RSI":
            results[name] = ind.rsi(source, period)
        elif itype == "ATR":
            _require(high, low, itype)
            results[name] = ind.atr(high, low, close, period)
        elif itype == "ADX":
            _require(high, low, itype)
            results[name] = ind.adx(high, low, close, period)
        elif itype == "MACD":
            line, signal, hist = ind.macd(
                source, spec.get("fast", 12), spec.get("slow", 26), spec.get("signal", 9)
            )
            outputs = spec.get("outputs", {})
            results[outputs.get("line", f"{name}_line")] = line
            results[outputs.get("signal", f"{name}_signal")] = signal
            results[outputs.get("hist", f"{name}_hist")] = hist
        elif itype == "BBANDS":
            upper, middle, lower = ind.bollinger_bands(source, period, spec.get("std", 2.0))
            outputs = spec.get("outputs", {})
            results[outputs.get("upper", f"{name}_upper")] = upper
            results[outputs.get("middle", f"{name}_middle")] = middle
            results[outputs.get("lower", f"{name}_lower")] = lower
        else:
            raise ValueError(f"不支援的指標類型: {itype}")

    return results


def _require(high, low, itype: str) -> None:
    if not high or not low:
        raise ValueError(f"{itype} 需要 high/low 價格序列")


def evaluate_stock(prices: PriceSeries, strategy: dict[str, Any]) -> dict[str, Any] | None:
    """對單一股票依策略計算最新一筆因子值。

    資料不足（新股上市未滿門檻天數）、指標計算失敗（如缺 high/low）、
    或未通過 filters，一律回傳 None，交由呼叫端排除，不拋例外中斷整批處理。
    """
    close = prices.get("close", [])
    min_history = strategy.get("universe", {}).get("min_history_days", 260)
    if len(close) < min_history:
        return None

    try:
        indicator_series = compute_indicators(prices, strategy.get("indicators", []))
    except ValueError:
        return None

    latest = len(close) - 1
    variables: dict[str, Any] = {}
    for field in ("open", "high", "low", "close", "volume"):
        series = prices.get(field)
        if series:
            variables[field] = series[latest]

    for name, series in indicator_series.items():
        variables[name] = series[latest] if latest < len(series) else None

    for factor in strategy.get("derived_factors", []):
        try:
            variables[factor["name"]] = safe_eval(factor["expression"], variables)
        except ExpressionError:
            variables[factor["name"]] = None

    for f in strategy.get("filters", []):
        try:
            passed = safe_eval(f["expression"], variables)
        except ExpressionError:
            return None
        if not passed:
            return None

    signals: dict[str, Any] = {}
    for sig in strategy.get("entry_signals", []):
        try:
            signals[sig["name"]] = safe_eval(sig["expression"], variables)
        except ExpressionError:
            signals[sig["name"]] = None
    for sig in strategy.get("exit_signals", []):
        try:
            signals[sig["name"]] = safe_eval(sig["expression"], variables)
        except ExpressionError:
            signals[sig["name"]] = None
    variables["signals"] = signals

    return variables


def rank_stocks(
    stock_prices: dict[str, PriceSeries],
    strategy: dict[str, Any],
    apply_position_limit: bool = True,
) -> list[dict[str, Any]]:
    """回傳依 ranking 因子排序的股票清單，格式穩定、同輸入必得同輸出（T1-4）。

    apply_position_limit=False 時忽略 `portfolio.max_positions`，回傳所有通過
    filters 的股票分數（供次日預測模組累積歷史分數使用，而不只是當日前十名）。
    """
    ranking = strategy.get("ranking", {})
    factor_name = ranking["factor"]
    descending = ranking.get("order", "desc") == "desc"

    scored: list[dict[str, Any]] = []
    for stock_id in sorted(stock_prices):  # 排序輸入 key，確保計算順序穩定、結果可重現
        prices = stock_prices[stock_id]
        variables = evaluate_stock(prices, strategy)
        if variables is None:
            continue
        score = variables.get(factor_name)
        if score is None:
            continue
        scored.append({"stock_id": stock_id, "score": score, "factors": variables})

    # scored 已依 stock_id 升冪插入；sort() 是穩定排序，同分時仍保留 stock_id 升冪順序（T1-4 可重現性）
    scored.sort(key=lambda row: row["score"], reverse=descending)

    max_positions = strategy.get("portfolio", {}).get("max_positions")
    if apply_position_limit and max_positions:
        scored = scored[:max_positions]

    return scored
