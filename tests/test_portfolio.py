"""持股快照與績效計算測試，對應 T3-1。"""

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.portfolio import build_holding, build_portfolio_snapshot, compute_performance_pct


def test_t3_1_performance_matches_manual_calculation():
    closes = [100 + i * 0.5 for i in range(30)]  # 每天 +0.5
    result = compute_performance_pct(closes)

    latest = closes[-1]
    expected_1d = (latest - closes[-2]) / closes[-2]
    expected_1w = (latest - closes[-6]) / closes[-6]
    expected_1m = (latest - closes[-21]) / closes[-21]

    assert math.isclose(result["1d_pct"], expected_1d)
    assert math.isclose(result["1w_pct"], expected_1w)
    assert math.isclose(result["1m_pct"], expected_1m)


def test_performance_returns_none_when_insufficient_history():
    closes = [100.0, 101.0, 102.0]
    result = compute_performance_pct(closes)
    assert result["1d_pct"] is not None
    assert result["1w_pct"] is None  # 只有 3 筆，不足 5 個交易日
    assert result["1m_pct"] is None


def test_build_holding_market_value_and_pnl():
    closes = [50.0, 52.0, 55.0]
    holding = build_holding(
        stock_id="2330", name="台積電", shares=100, cost_basis=50.0, closes=closes, pe_ratio=18.5
    )
    assert holding["current_price"] == 55.0
    assert holding["market_value"] == 5500.0
    assert math.isclose(holding["unrealized_pnl_pct"], (55.0 - 50.0) / 50.0)
    assert holding["pe_ratio"] == 18.5


def test_build_holding_zero_cost_basis_does_not_crash():
    holding = build_holding(
        stock_id="X", name="測試", shares=10, cost_basis=0.0, closes=[10.0, 11.0]
    )
    assert holding["unrealized_pnl_pct"] is None


def test_build_portfolio_snapshot_totals_and_percentages():
    holdings_input = [
        {"stock_id": "2330", "name": "台積電", "shares": 100, "cost_basis": 500.0},
        {"stock_id": "2317", "name": "鴻海", "shares": 200, "cost_basis": 100.0},
    ]
    price_data = {
        "2330": [500.0, 510.0, 520.0],
        "2317": [100.0, 105.0, 110.0],
    }
    snapshot = build_portfolio_snapshot(cash=10000.0, holdings_input=holdings_input, price_data=price_data)

    expected_2330_mv = 100 * 520.0
    expected_2317_mv = 200 * 110.0
    expected_total_mv = expected_2330_mv + expected_2317_mv
    expected_total_value = 10000.0 + expected_total_mv

    assert math.isclose(snapshot["total_market_value"], expected_total_mv)
    assert math.isclose(snapshot["total_value"], expected_total_value)
    assert math.isclose(snapshot["cash"]["pct_of_total"], 10000.0 / expected_total_value)

    total_pct = snapshot["cash"]["pct_of_total"] + sum(
        h["pct_of_portfolio"] for h in snapshot["holdings"]
    )
    assert math.isclose(total_pct, 1.0)
