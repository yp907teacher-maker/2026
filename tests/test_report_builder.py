"""report.json 產生與歷史儲存測試，對應 T3-2、T3-3。"""

import json
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.portfolio import build_portfolio_snapshot
from src.report_builder import build_report, load_report, report_path, save_report
from src.report_schema import validate_report
from jsonschema.exceptions import ValidationError


def make_sample_report(date: str) -> dict:
    price_data = {"2330": [500.0, 510.0, 520.0], "2317": [100.0, 105.0, 110.0]}
    holdings_input = [
        {"stock_id": "2330", "name": "台積電", "shares": 100, "cost_basis": 500.0},
        {"stock_id": "2317", "name": "鴻海", "shares": 200, "cost_basis": 100.0},
    ]
    snapshot = build_portfolio_snapshot(cash=10000.0, holdings_input=holdings_input, price_data=price_data)

    return build_report(
        date=date,
        portfolio_snapshot=snapshot,
        top10=[{"stock_id": "2330", "score": 0.12}, {"stock_id": "2317", "score": 0.08}],
        predictions={
            "lookback": 5,
            "top_n": 10,
            "items": [{"stock_id": "2330", "predicted_score": 0.13, "confidence": 62.5}],
        },
        watched_sectors=[
            {"sector": "半導體", "representative_stocks": ["2330"], "today_pct_change": 0.012}
        ],
        nav_history=[{"date": date, "nav": 1.05, "drawdown_pct": -0.02}],
        generated_at=f"{date}T06:00:00+08:00",
    )


@pytest.fixture
def tmp_reports_dir():
    d = tempfile.mkdtemp()
    yield Path(d)
    shutil.rmtree(d, ignore_errors=True)


def test_t3_3_report_passes_schema_validation():
    report = make_sample_report("2026-08-03")
    validate_report(report)  # 不拋例外即為通過


def test_t3_3_invalid_report_fails_schema_validation():
    broken = {"date": "2026-08-03"}  # 缺少必填欄位
    with pytest.raises(ValidationError):
        validate_report(broken)


def test_t3_2_five_consecutive_days_produce_independent_reports(tmp_reports_dir):
    dates = [f"2026-08-{d:02d}" for d in range(3, 8)]  # 連續 5 天

    for date in dates:
        report = make_sample_report(date)
        save_report(report, base_dir=tmp_reports_dir)

    for date in dates:
        path = report_path(date, base_dir=tmp_reports_dir)
        assert path.exists()

        loaded = load_report(date, base_dir=tmp_reports_dir)
        assert loaded["date"] == date  # 每天資料對應到自己的日期，未互相覆蓋

    all_dirs = sorted(p.name for p in tmp_reports_dir.iterdir())
    assert all_dirs == dates


def test_save_report_overwrites_same_day_only(tmp_reports_dir):
    date = "2026-08-03"
    report_v1 = make_sample_report(date)
    report_v1["total_value"] = 1111.0
    save_report(report_v1, base_dir=tmp_reports_dir)

    report_v2 = make_sample_report(date)
    report_v2["total_value"] = 2222.0
    save_report(report_v2, base_dir=tmp_reports_dir)

    loaded = load_report(date, base_dir=tmp_reports_dir)
    assert loaded["total_value"] == 2222.0

    all_dirs = list(tmp_reports_dir.iterdir())
    assert len(all_dirs) == 1  # 同一天不會產生第二個資料夾


def test_report_json_round_trips(tmp_reports_dir):
    report = make_sample_report("2026-08-03")
    path = save_report(report, base_dir=tmp_reports_dir)

    with open(path, encoding="utf-8") as fh:
        raw = json.load(fh)
    assert raw == report
