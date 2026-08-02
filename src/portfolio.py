"""追蹤組合（現金＋持股）快照計算：市值、佔比、績效%，供 report_builder 組裝 report.json。

持股資料一律由使用者手動輸入（股數、成本），非真實下單帳戶，
與 fubon_client.py（本機查詢實際富邦帳戶持股）用途不同。
"""

from __future__ import annotations

# 台股一週約 5 個交易日、一個月約 20 個交易日，績效% 用「交易日往回數」而非
# 日曆天，避免假日造成的誤差。
PERFORMANCE_OFFSETS = {"1d_pct": 1, "1w_pct": 5, "1m_pct": 20}


def compute_performance_pct(closes: list[float]) -> dict[str, float | None]:
    """依收盤價序列（舊到新）計算 1日/1週/1月報酬率；資料不足回傳 None。"""
    if not closes:
        return {label: None for label in PERFORMANCE_OFFSETS}

    latest = closes[-1]
    result: dict[str, float | None] = {}
    for label, offset in PERFORMANCE_OFFSETS.items():
        idx = len(closes) - 1 - offset
        if idx < 0:
            result[label] = None
            continue
        base = closes[idx]
        result[label] = None if base == 0 else (latest - base) / base
    return result


def build_holding(
    stock_id: str,
    name: str,
    shares: float,
    cost_basis: float,
    closes: list[float],
    pe_ratio: float | None = None,
) -> dict:
    """組裝單一持股欄位。closes 需為該股票的收盤價序列（舊到新），最後一筆為現價。"""
    if not closes:
        raise ValueError(f"{stock_id} 缺少價格資料，無法組裝持股")

    current_price = closes[-1]
    market_value = shares * current_price
    unrealized_pnl_pct = None if cost_basis == 0 else (current_price - cost_basis) / cost_basis

    return {
        "stock_id": stock_id,
        "name": name,
        "shares": shares,
        "cost_basis": cost_basis,
        "current_price": current_price,
        "market_value": market_value,
        "unrealized_pnl_pct": unrealized_pnl_pct,
        "performance": compute_performance_pct(closes),
        "pe_ratio": pe_ratio,
    }


def build_portfolio_snapshot(
    cash: float,
    holdings_input: list[dict],
    price_data: dict[str, list[float]],
    pe_data: dict[str, float] | None = None,
) -> dict:
    """組裝現金＋持股快照，含市值、總資產、各項佔比。

    holdings_input：每筆 {"stock_id","name","shares","cost_basis"}。
    price_data：{stock_id: [收盤價...]}（舊到新）。
    """
    pe_data = pe_data or {}
    holdings = [
        build_holding(
            stock_id=h["stock_id"],
            name=h["name"],
            shares=h["shares"],
            cost_basis=h["cost_basis"],
            closes=price_data[h["stock_id"]],
            pe_ratio=pe_data.get(h["stock_id"]),
        )
        for h in holdings_input
    ]

    total_market_value = sum(h["market_value"] for h in holdings)
    total_value = cash + total_market_value

    for h in holdings:
        h["pct_of_portfolio"] = (
            h["market_value"] / total_value if total_value else None
        )

    return {
        "cash": {
            "amount": cash,
            "pct_of_total": cash / total_value if total_value else None,
        },
        "holdings": holdings,
        "total_market_value": total_market_value,
        "total_value": total_value,
    }
