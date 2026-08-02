"""關注類股當日表現彙整，供 report.json 的 watched_sectors 欄位使用。"""

from __future__ import annotations

from .portfolio import compute_performance_pct


def build_watched_sectors(
    sector_configs: list[dict], price_data: dict[str, list[float]]
) -> list[dict]:
    """依設定檔（每個類股的代表股清單）與價格資料，算出各類股當日平均漲跌幅。

    sector_configs：每筆 {"sector": str, "representative_stocks": [stock_id, ...]}。
    某代表股缺價格資料或資料不足時直接跳過該股，不中斷整體計算；
    若整個類股都沒有可用資料，today_pct_change 回傳 None 而非拋例外。
    """
    results = []
    for cfg in sector_configs:
        changes = []
        for stock_id in cfg["representative_stocks"]:
            closes = price_data.get(stock_id)
            if not closes:
                continue
            perf = compute_performance_pct(closes)
            if perf["1d_pct"] is not None:
                changes.append(perf["1d_pct"])

        today_pct_change = sum(changes) / len(changes) if changes else None
        results.append(
            {
                "sector": cfg["sector"],
                "representative_stocks": cfg["representative_stocks"],
                "today_pct_change": today_pct_change,
            }
        )
    return results
