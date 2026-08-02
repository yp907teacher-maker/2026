"""再平衡觸發規則：新資金匯入時、每月第一個交易日各觸發一次，其餘時間不觸發。

計劃書明確要求「移除固定週頻率，避免過度交易」，所以這裡刻意不做「每 N 天」
之類的排程，只有這兩種事件驅動的觸發點。同一天最多觸發一次；同一個月只會
因為「當月第一個交易日」觸發一次，即使呼叫端不小心把同月的其他天也標成
第一個交易日，也不會重複觸發（月份配額在任一原因的觸發發生在真正的第一個
交易日時就視為已使用）。
"""

from __future__ import annotations


def check_rebalance(
    today: str,
    is_first_trading_day_of_month: bool,
    new_cash_inflow: bool,
    state: dict | None,
) -> tuple[bool, str | None, dict]:
    """單日判定，狀態（上次觸發日期／上次觸發月份）由呼叫端跨日持久化。

    回傳 (是否觸發, 觸發原因, 更新後狀態)。state 為 None 視為全新開始
    （尚未有任何觸發紀錄），供每日排程腳本第一次執行時使用。
    """
    state = dict(state) if state else {}
    last_rebalance_date = state.get("last_rebalance_date")
    last_monthly_trigger_month = state.get("last_monthly_trigger_month")
    month = today[:7]

    triggered = False
    reason: str | None = None

    if today == last_rebalance_date:
        triggered, reason = False, None
    elif new_cash_inflow:
        triggered, reason = True, "new_cash_inflow"
    elif is_first_trading_day_of_month and month != last_monthly_trigger_month:
        triggered, reason = True, "monthly_first_trading_day"

    if triggered:
        last_rebalance_date = today
        if is_first_trading_day_of_month:
            last_monthly_trigger_month = month

    new_state = {
        "last_rebalance_date": last_rebalance_date,
        "last_monthly_trigger_month": last_monthly_trigger_month,
    }
    return triggered, reason, new_state


def run_rebalance_calendar(days: list[dict]) -> list[dict]:
    """依序處理一串交易日事件，回傳每天的觸發結果（測試／回測用，非每日排程用）。

    days：每筆 {"date": "YYYY-MM-DD", "is_first_trading_day_of_month": bool,
    "new_cash_inflow": bool}，需已依日期由舊到新排序。

    回傳：每筆 {"date", "triggered", "reason"}，reason 為
    "new_cash_inflow" / "monthly_first_trading_day" / None。
    """
    results: list[dict] = []
    state: dict = {}

    for day in days:
        triggered, reason, state = check_rebalance(
            today=day["date"],
            is_first_trading_day_of_month=day["is_first_trading_day_of_month"],
            new_cash_inflow=day["new_cash_inflow"],
            state=state,
        )
        results.append({"date": day["date"], "triggered": triggered, "reason": reason})

    return results
