"""report.json 去敏感化測試：確保公開版不會洩漏絕對金額。"""

import shutil
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.portfolio import build_portfolio_snapshot
from src.report_builder import build_report, load_public_report, public_report_path, save_public_report
from src.report_schema import build_public_report, validate_public_report


def make_sample_report() -> dict:
    price_data = {"2330": [500.0, 510.0, 520.0], "2317": [100.0, 105.0, 110.0]}
    holdings_input = [
        {"stock_id": "2330", "name": "台積電", "shares": 100, "cost_basis": 500.0},
        {"stock_id": "2317", "name": "鴻海", "shares": 200, "cost_basis": 100.0},
    ]
    snapshot = build_portfolio_snapshot(cash=10000.0, holdings_input=holdings_input, price_data=price_data)
    return build_report(
        date="2026-08-03",
        portfolio_snapshot=snapshot,
        top10=[{"stock_id": "2330", "score": 0.12}],
        predictions={"lookback": 5, "top_n": 10, "items": []},
        watched_sectors=[{"sector": "半導體", "representative_stocks": ["2330"], "today_pct_change": 0.01}],
        nav_history=[{"date": "2026-08-03", "nav": 1.0, "drawdown_pct": 0.0}],
        benchmark_nav_history=[{"date": "2026-08-03", "nav": 1.0}],
    )


def test_public_report_strips_absolute_amounts():
    report = make_sample_report()
    public = build_public_report(report)

    assert "total_market_value" not in public
    assert "total_value" not in public
    assert "amount" not in public["cash"]

    for holding in public["holdings"]:
        assert "shares" not in holding
        assert "cost_basis" not in holding
        assert "current_price" not in holding
        assert "market_value" not in holding


def test_public_report_keeps_relative_and_non_sensitive_fields():
    report = make_sample_report()
    public = build_public_report(report)

    assert public["cash"]["pct_of_total"] == report["cash"]["pct_of_total"]
    assert public["top10"] == report["top10"]
    assert public["predictions"] == report["predictions"]
    assert public["watched_sectors"] == report["watched_sectors"]
    assert public["nav_history"] == report["nav_history"]

    holding = next(h for h in public["holdings"] if h["stock_id"] == "2330")
    original = next(h for h in report["holdings"] if h["stock_id"] == "2330")
    assert holding["pct_of_portfolio"] == original["pct_of_portfolio"]
    assert holding["unrealized_pnl_pct"] == original["unrealized_pnl_pct"]
    assert holding["performance"] == original["performance"]


def test_public_report_passes_its_own_schema():
    report = make_sample_report()
    public = build_public_report(report)
    validate_public_report(public)  # 不拋例外即通過


@pytest.fixture
def tmp_dir():
    d = tempfile.mkdtemp()
    yield Path(d)
    shutil.rmtree(d, ignore_errors=True)


def test_save_and_load_public_report_round_trips(tmp_dir):
    report = make_sample_report()
    path = save_public_report(report, base_dir=tmp_dir)

    assert path == public_report_path("2026-08-03", base_dir=tmp_dir)
    assert path.exists()

    loaded = load_public_report("2026-08-03", base_dir=tmp_dir)
    assert "total_value" not in loaded
    assert loaded["date"] == "2026-08-03"


def test_public_report_output_cannot_reconstruct_absolute_value(tmp_dir):
    """確保光看公開版檔案的字串內容，找不到任何金額數字（防止漏改欄位）。"""
    report = make_sample_report()
    path = save_public_report(report, base_dir=tmp_dir)
    raw = path.read_text(encoding="utf-8")

    assert "10000" not in raw  # cash amount
    assert "52000" not in raw  # 2330 market_value (100*520)
    assert "22000" not in raw  # 2317 market_value (200*110)
