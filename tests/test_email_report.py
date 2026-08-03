"""Email HTML 渲染測試，對應 T5-2（內容與 Model 一致）、T5-4（資料不完整提醒）。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.email_report import build_email_html, build_email_subject


def make_sample_report(**overrides) -> dict:
    report = {
        "date": "2026-08-03",
        "generated_at": "2026-08-03T06:00:00+08:00",
        "cash": {"amount": 18349.0, "pct_of_total": 0.111},
        "holdings": [
            {
                "stock_id": "2330",
                "name": "台積電",
                "shares": 4.0,
                "cost_basis": 1757.5,
                "current_price": 2425.0,
                "market_value": 9700.0,
                "unrealized_pnl_pct": 0.38,
                "pct_of_portfolio": 0.066,
                "pe_ratio": 32.6,
                "performance": {"1d_pct": 0.0998, "1w_pct": 0.0319, "1m_pct": -0.0162},
            },
            {
                "stock_id": "3105",
                "name": "穩懋",
                "shares": 20.0,
                "cost_basis": 509.7,
                "current_price": 294.5,
                "market_value": 5890.0,
                "unrealized_pnl_pct": -0.42,
                "pct_of_portfolio": 0.04,
                "pe_ratio": 56.42,
                "performance": {"1d_pct": 0.0989, "1w_pct": -0.1376, "1m_pct": -0.2835},
            },
        ],
        "total_market_value": 147258.5,
        "total_value": 165607.5,
        "top10": [{"stock_id": "3231", "score": 0.1201}, {"stock_id": "2884", "score": 0.0862}],
        "predictions": {
            "lookback": 5,
            "top_n": 10,
            "items": [{"stock_id": "3231", "predicted_score": 0.13, "confidence": 62.5}],
        },
        "watched_sectors": [
            {"sector": "半導體", "representative_stocks": ["2330", "2454", "3711"], "today_pct_change": 0.0992}
        ],
        "nav_history": [
            {"date": "2026-08-02", "nav": 1.0, "drawdown_pct": 0.0},
            {"date": "2026-08-03", "nav": 1.05, "drawdown_pct": 0.0},
        ],
        "benchmark_nav_history": [
            {"date": "2026-08-02", "nav": 1.0},
            {"date": "2026-08-03", "nav": 1.02},
        ],
        "rebalance": {"triggered": False, "reason": None},
    }
    report.update(overrides)
    return report


def test_subject_contains_date():
    report = make_sample_report()
    subject = build_email_subject(report)
    assert "2026-08-03" in subject


def test_html_contains_key_sections():
    report = make_sample_report()
    html = build_email_html(report)

    assert "165,608" in html or "165,607" in html  # total_value 千分位格式
    assert "2330" in html and "台積電" in html
    assert "3231" in html  # top10 / predictions 都有這檔
    assert "半導體" in html
    assert "不構成投資建議" in html  # 固定風險聲明


def test_stop_loss_alert_triggers_for_large_loss():
    report = make_sample_report()  # 3105 虧損 42%，超過預設 -15% 停損門檻
    html = build_email_html(report)
    assert "停損" in html
    assert "3105" in html.split("重要訊號提醒")[1][:500]


def test_take_profit_alert_triggers_for_large_gain():
    report = make_sample_report()
    report["holdings"][0]["unrealized_pnl_pct"] = 0.35  # 超過預設 +30% 停利門檻
    html = build_email_html(report)
    assert "停利" in html


def test_no_alert_when_within_thresholds():
    report = make_sample_report()
    report["holdings"][0]["unrealized_pnl_pct"] = 0.05
    report["holdings"][1]["unrealized_pnl_pct"] = -0.05
    html = build_email_html(report)
    assert "沒有持股觸及" in html


def test_t5_4_data_warnings_rendered_when_present():
    report = make_sample_report()
    html = build_email_html(report, data_warnings=["2454 資料抓取失敗，未列入今日排名/預測"])
    assert "資料不完整提醒" in html
    assert "2454" in html


def test_no_warnings_banner_when_data_complete():
    report = make_sample_report()
    html = build_email_html(report, data_warnings=None)
    assert "資料不完整提醒" not in html


def test_handles_empty_holdings_and_predictions_without_crashing():
    report = make_sample_report(holdings=[], top10=[], predictions={"lookback": 5, "top_n": 10, "items": []})
    html = build_email_html(report)
    assert "目前沒有持股資料" in html
    assert "尚無排名資料" in html
    assert "暫無預測名單" in html
