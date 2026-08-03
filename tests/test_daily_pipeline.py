"""每日整合腳本的核心邏輯測試（run_pipeline 是純函式，不需要網路）。

對應「連續多天執行整合腳本，report.json 正確產生且各天資料互不污染」的
端到端驗證，取代 T3-2／T3-4 原本只用零散單元測試涵蓋、缺乏整合驗證的缺口。
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.daily_pipeline import run_pipeline
from src.report_schema import validate_report


def _wave(i: int, period: int = 10, amplitude: float = 2.0) -> float:
    half = period / 2
    phase = i % period
    if phase <= half:
        return -amplitude + (2 * amplitude / half) * phase
    return amplitude - (2 * amplitude / half) * (phase - half)


def make_price_lookup(n_days: int = 300) -> dict:
    stock_ids = ["0050", "2330", "2454", "3711", "3231", "2382", "6669", "2882", "2881", "2891"]
    lookup = {}
    for s, stock_id in enumerate(stock_ids):
        trend = 0.05 + s * 0.01
        closes = [round(100 + trend * i + _wave(i + s), 2) for i in range(n_days)]
        highs = [round(c * 1.01, 2) for c in closes]
        lows = [round(c * 0.99, 2) for c in closes]
        lookup[stock_id] = {"close": closes, "high": highs, "low": lows}
    return lookup


def load_strategy() -> dict:
    strategies_dir = Path(__file__).resolve().parent.parent / "strategies"
    with open(strategies_dir / "strategy_momentum.json", encoding="utf-8") as fh:
        return json.load(fh)


def base_kwargs(price_lookup: dict) -> dict:
    return {
        "universe_stock_ids": ["0050", "2330", "2454", "3711", "3231", "2382", "6669", "2882", "2881", "2891"],
        "holdings_config": {
            "cash": 50000,
            "holdings": [{"stock_id": "2330", "name": "台積電", "shares": 100, "cost_basis": 90.0}],
            "new_cash_inflow_today": False,
        },
        "watched_sectors_config": [
            {"sector": "半導體", "representative_stocks": ["2330", "2454", "3711"]},
            {"sector": "AI", "representative_stocks": ["3231", "2382", "6669"]},
            {"sector": "金融", "representative_stocks": ["2882", "2881", "2891"]},
        ],
        "strategy": load_strategy(),
        "price_lookup": price_lookup,
        "pe_lookup": {"2330": 22.5},
    }


def test_single_run_produces_valid_report():
    price_lookup = make_price_lookup()
    result = run_pipeline(
        report_date="2026-08-03",
        is_first_trading_day_of_month=False,
        previous_report=None,
        score_history=[],
        nav_state=None,
        rebalance_state=None,
        **base_kwargs(price_lookup),
    )

    report = result["report"]
    validate_report(report)  # 不拋例外即通過 T3-3
    assert report["date"] == "2026-08-03"
    assert len(report["holdings"]) == 1
    assert report["holdings"][0]["stock_id"] == "2330"
    assert report["nav_history"][-1]["nav"] == 1.0  # 第一天，NAV 基準
    assert report["rebalance"] == {"triggered": False, "reason": None}
    assert 0 <= len(report["top10"]) <= 10
    assert {s["sector"] for s in report["watched_sectors"]} == {"半導體", "AI", "金融"}


def test_five_consecutive_days_do_not_cross_contaminate():
    price_lookup = make_price_lookup()
    dates = [f"2026-08-{d:02d}" for d in range(3, 8)]

    score_history: list = []
    nav_state = None
    rebalance_state = None
    previous_report = None
    reports = {}

    for i, date in enumerate(dates):
        result = run_pipeline(
            report_date=date,
            is_first_trading_day_of_month=(i == 0),
            previous_report=previous_report,
            score_history=score_history,
            nav_state=nav_state,
            rebalance_state=rebalance_state,
            **base_kwargs(price_lookup),
        )
        reports[date] = result["report"]
        score_history = result["score_history"]
        nav_state = result["nav_state"]
        rebalance_state = result["rebalance_state"]
        previous_report = result["report"]

    for date in dates:
        assert reports[date]["date"] == date
        validate_report(reports[date])

    # 每天各自對應自己的日期，nav_history 逐日累積不是互相覆蓋
    assert [h["date"] for h in reports[dates[-1]]["nav_history"]] == dates

    # 只有第一天（當月第一個交易日）觸發再平衡，其餘 4 天都不該再觸發
    triggered_days = [d for d in dates if reports[d]["rebalance"]["triggered"]]
    assert triggered_days == [dates[0]]

    # 分數歷史應累積到 5 天，可以餵給 predictor
    assert len(score_history) == 5


def test_new_cash_inflow_triggers_rebalance_mid_month():
    price_lookup = make_price_lookup()
    kwargs = base_kwargs(price_lookup)
    kwargs["holdings_config"] = dict(kwargs["holdings_config"], new_cash_inflow_today=True)

    result = run_pipeline(
        report_date="2026-08-15",
        is_first_trading_day_of_month=False,
        previous_report=None,
        score_history=[],
        nav_state=None,
        rebalance_state=None,
        **kwargs,
    )
    assert result["report"]["rebalance"] == {"triggered": True, "reason": "new_cash_inflow"}


def test_missing_stock_in_price_lookup_does_not_crash():
    price_lookup = make_price_lookup()
    del price_lookup["6669"]  # 模擬其中一檔抓取失敗

    result = run_pipeline(
        report_date="2026-08-03",
        is_first_trading_day_of_month=False,
        previous_report=None,
        score_history=[],
        nav_state=None,
        rebalance_state=None,
        **base_kwargs(price_lookup),
    )
    report = result["report"]
    validate_report(report)
    ai_sector = next(s for s in report["watched_sectors"] if s["sector"] == "AI")
    assert ai_sector["today_pct_change"] is not None  # 其餘兩檔代表股仍能算出平均


def test_benchmark_nav_history_tracks_0050_independently_of_portfolio():
    """對應 T4-3：NAV 曲線需要能疊加大盤（0050）對比，這裡驗證後端資料正確累積。"""
    price_lookup = make_price_lookup()
    dates = [f"2026-08-{d:02d}" for d in range(3, 6)]

    benchmark_nav_state = None
    previous_report = None
    reports = {}

    for i, date in enumerate(dates):
        result = run_pipeline(
            report_date=date,
            is_first_trading_day_of_month=(i == 0),
            previous_report=previous_report,
            score_history=[],
            nav_state=None,
            rebalance_state=None,
            benchmark_nav_state=benchmark_nav_state,
            **base_kwargs(price_lookup),
        )
        reports[date] = result["report"]
        benchmark_nav_state = result["benchmark_nav_state"]
        previous_report = result["report"]

    # benchmark 曲線第一天基準為 1.0，且會逐日累積，跟 portfolio nav_history 分開維護
    assert reports[dates[0]]["benchmark_nav_history"][0]["nav"] == 1.0
    assert [h["date"] for h in reports[dates[-1]]["benchmark_nav_history"]] == dates
    # 0050 沒有任何私人資料相依，只跟自己的股價序列有關
    assert all("drawdown_pct" not in h for h in reports[dates[-1]]["benchmark_nav_history"])


def test_benchmark_missing_does_not_crash_pipeline():
    price_lookup = make_price_lookup()
    del price_lookup["0050"]  # 模擬大盤基準股抓取失敗

    result = run_pipeline(
        report_date="2026-08-03",
        is_first_trading_day_of_month=False,
        previous_report=None,
        score_history=[],
        nav_state=None,
        rebalance_state=None,
        **base_kwargs(price_lookup),
    )
    report = result["report"]
    validate_report(report)
    assert report["benchmark_nav_history"] == []


def test_load_nav_state_uses_local_file_without_token(monkeypatch, tmp_path):
    import scripts.daily_pipeline as pipeline

    monkeypatch.delenv("STATE_REPO_TOKEN", raising=False)
    monkeypatch.setattr(pipeline, "REPORTS_DIR", tmp_path)
    fake_path = tmp_path / "nav_state.json"
    fake_path.write_text('{"baseline_total_value": 100000.0, "peak_nav": 1.0}', encoding="utf-8")

    paths = pipeline.PortfolioPaths("default")
    result = pipeline._load_nav_state(paths)
    assert result == {"baseline_total_value": 100000.0, "peak_nav": 1.0}


def test_load_nav_state_uses_private_repo_when_token_set(monkeypatch):
    import scripts.daily_pipeline as pipeline

    monkeypatch.setenv("STATE_REPO_TOKEN", "fake-token")
    calls = {}

    def fake_pull_state(repo, path, token):
        calls["args"] = (repo, path, token)
        return {"baseline_total_value": 999.0, "peak_nav": 1.2}

    monkeypatch.setattr("src.state_sync.pull_state", fake_pull_state)

    paths = pipeline.PortfolioPaths("default")
    result = pipeline._load_nav_state(paths)
    assert result == {"baseline_total_value": 999.0, "peak_nav": 1.2}
    assert calls["args"] == (pipeline.STATE_REPO, pipeline.STATE_REPO_PATH, "fake-token")


def test_load_nav_state_uses_separate_key_for_non_default_portfolio(monkeypatch):
    import scripts.daily_pipeline as pipeline

    monkeypatch.setenv("STATE_REPO_TOKEN", "fake-token")
    calls = {}

    def fake_pull_state(repo, path, token):
        calls["args"] = (repo, path, token)
        return None

    monkeypatch.setattr("src.state_sync.pull_state", fake_pull_state)

    paths = pipeline.PortfolioPaths("example_meanreversion")
    pipeline._load_nav_state(paths)
    assert calls["args"] == (
        pipeline.STATE_REPO,
        "example_meanreversion/nav_state.json",
        "fake-token",
    )


def test_save_nav_state_uses_local_file_without_token(monkeypatch, tmp_path):
    import json as json_module

    import scripts.daily_pipeline as pipeline

    monkeypatch.delenv("STATE_REPO_TOKEN", raising=False)
    monkeypatch.setattr(pipeline, "REPORTS_DIR", tmp_path)

    paths = pipeline.PortfolioPaths("default")
    pipeline._save_nav_state({"baseline_total_value": 5000.0, "peak_nav": 1.1}, "2026-08-03", paths)

    assert json_module.loads((tmp_path / "nav_state.json").read_text(encoding="utf-8")) == {
        "baseline_total_value": 5000.0,
        "peak_nav": 1.1,
    }


def test_save_nav_state_uses_private_repo_when_token_set(monkeypatch):
    import scripts.daily_pipeline as pipeline

    monkeypatch.setenv("STATE_REPO_TOKEN", "fake-token")
    calls = {}

    def fake_push_state(repo, path, token, data, message=""):
        calls["args"] = (repo, path, token, data, message)

    monkeypatch.setattr("src.state_sync.push_state", fake_push_state)

    paths = pipeline.PortfolioPaths("default")
    pipeline._save_nav_state({"baseline_total_value": 5000.0}, "2026-08-03", paths)

    repo, path, token, data, message = calls["args"]
    assert repo == pipeline.STATE_REPO
    assert path == pipeline.STATE_REPO_PATH
    assert token == "fake-token"
    assert data == {"baseline_total_value": 5000.0}
    assert "2026-08-03" in message
