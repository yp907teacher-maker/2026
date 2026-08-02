"""再平衡觸發規則測試，對應 T3-4：模擬「新資金匯入」與「跨月」情境，
驗證再平衡邏輯正確觸發且僅觸發一次。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.rebalance import run_rebalance_calendar


def test_t3_4_monthly_first_trading_day_triggers_once():
    days = [
        {"date": "2026-08-03", "is_first_trading_day_of_month": True, "new_cash_inflow": False},
        {"date": "2026-08-04", "is_first_trading_day_of_month": False, "new_cash_inflow": False},
        {"date": "2026-08-05", "is_first_trading_day_of_month": False, "new_cash_inflow": False},
    ]
    results = run_rebalance_calendar(days)

    assert results[0] == {"date": "2026-08-03", "triggered": True, "reason": "monthly_first_trading_day"}
    assert results[1]["triggered"] is False
    assert results[2]["triggered"] is False


def test_t3_4_new_cash_inflow_triggers_immediately():
    days = [
        {"date": "2026-08-10", "is_first_trading_day_of_month": False, "new_cash_inflow": True},
        {"date": "2026-08-11", "is_first_trading_day_of_month": False, "new_cash_inflow": False},
    ]
    results = run_rebalance_calendar(days)

    assert results[0] == {"date": "2026-08-10", "triggered": True, "reason": "new_cash_inflow"}
    assert results[1]["triggered"] is False


def test_t3_4_cross_month_and_cash_inflow_combined_triggers_only_once_per_day():
    # 同一天同時符合「當月第一個交易日」與「新資金匯入」，仍只算一次觸發
    days = [
        {"date": "2026-09-01", "is_first_trading_day_of_month": True, "new_cash_inflow": True},
        {"date": "2026-09-02", "is_first_trading_day_of_month": False, "new_cash_inflow": False},
    ]
    results = run_rebalance_calendar(days)

    triggered_days = [r for r in results if r["triggered"]]
    assert len(triggered_days) == 1
    assert triggered_days[0]["date"] == "2026-09-01"
    assert triggered_days[0]["reason"] == "new_cash_inflow"


def test_t3_4_monthly_quota_not_reused_even_if_flag_set_twice_same_month():
    # 呼叫端誤把同一個月的兩天都標成「當月第一個交易日」，仍只觸發一次
    days = [
        {"date": "2026-08-03", "is_first_trading_day_of_month": True, "new_cash_inflow": False},
        {"date": "2026-08-04", "is_first_trading_day_of_month": True, "new_cash_inflow": False},
    ]
    results = run_rebalance_calendar(days)

    triggered_days = [r for r in results if r["triggered"]]
    assert len(triggered_days) == 1
    assert triggered_days[0]["date"] == "2026-08-03"


def test_t3_4_new_month_after_cash_triggered_first_trading_day_still_triggers_next_month():
    # 8月第一個交易日剛好也是資金匯入日，9月第一個交易日應仍能正常觸發（配額是逐月重置的）
    days = [
        {"date": "2026-08-03", "is_first_trading_day_of_month": True, "new_cash_inflow": True},
        {"date": "2026-08-15", "is_first_trading_day_of_month": False, "new_cash_inflow": False},
        {"date": "2026-09-01", "is_first_trading_day_of_month": True, "new_cash_inflow": False},
    ]
    results = run_rebalance_calendar(days)

    assert results[0]["triggered"] is True and results[0]["reason"] == "new_cash_inflow"
    assert results[1]["triggered"] is False
    assert results[2]["triggered"] is True and results[2]["reason"] == "monthly_first_trading_day"


def test_t3_4_no_daily_rebalance_outside_events():
    days = [
        {"date": f"2026-08-{d:02d}", "is_first_trading_day_of_month": d == 3, "new_cash_inflow": False}
        for d in range(3, 20)
    ]
    results = run_rebalance_calendar(days)

    triggered_count = sum(1 for r in results if r["triggered"])
    assert triggered_count == 1  # 除了當月第一個交易日，其餘時間都不再平衡
