"""再平衡觸發規則：新資金匯入時、每月第一個交易日各觸發一次，其餘時間不觸發。

計劃書明確要求「移除固定週頻率，避免過度交易」，所以這裡刻意不做「每 N 天」
之類的排程，只有這兩種事件驅動的觸發點。同一天最多觸發一次；同一個月只會
因為「當月第一個交易日」觸發一次，即使呼叫端不小心把同月的其他天也標成
第一個交易日，也不會重複觸發（月份配額在任一原因的觸發發生在真正的第一個
交易日時就視為已使用）。
"""

from __future__ import annotations


def run_rebalance_calendar(days: list[dict]) -> list[dict]:
    """依序處理一串交易日事件，回傳每天的觸發結果。

    days：每筆 {"date": "YYYY-MM-DD", "is_first_trading_day_of_month": bool,
    "new_cash_inflow": bool}，需已依日期由舊到新排序。

    回傳：每筆 {"date", "triggered", "reason"}，reason 為
    "new_cash_inflow" / "monthly_first_trading_day" / None。
    """
    results: list[dict] = []
    last_rebalance_date: str | None = None
    last_monthly_trigger_month: str | None = None

    for day in days:
        today = day["date"]
        month = today[:7]
        new_cash_inflow = day["new_cash_inflow"]
        is_first_trading_day = day["is_first_trading_day_of_month"]

        triggered = False
        reason: str | None = None

        if today == last_rebalance_date:
            triggered, reason = False, None
        elif new_cash_inflow:
            triggered, reason = True, "new_cash_inflow"
        elif is_first_trading_day and month != last_monthly_trigger_month:
            triggered, reason = True, "monthly_first_trading_day"

        if triggered:
            last_rebalance_date = today
            if is_first_trading_day:
                last_monthly_trigger_month = month

        results.append({"date": today, "triggered": triggered, "reason": reason})

    return results
