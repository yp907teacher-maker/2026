"""Phase 6 多組合支援測試：對應 T6-1（互不干擾）、T6-2（換策略後排名改變）、
T6-3（錯誤隔離）、T6-4（端到端整合）。全部用合成資料，不需要網路。
"""

import json
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import scripts.daily_pipeline as pipeline
from scripts.daily_pipeline import (
    PortfolioPaths,
    _load_portfolio_configs,
    process_portfolio,
    run_portfolios,
)
from src.report_schema import validate_public_report, validate_report


def _wave(i: int, period: int = 10, amplitude: float = 2.0) -> float:
    half = period / 2
    phase = i % period
    if phase <= half:
        return -amplitude + (2 * amplitude / half) * phase
    return amplitude - (2 * amplitude / half) * (phase - half)


def make_price_lookup(n_days: int = 300) -> dict:
    stock_ids = ["0050", "2330", "2454", "3711", "3231", "2382", "6669", "2882", "2881", "2891", "2317"]
    lookup = {}
    for s, stock_id in enumerate(stock_ids):
        trend = 0.05 + s * 0.01
        closes = [round(100 + trend * i + _wave(i + s), 2) for i in range(n_days)]
        highs = [round(c * 1.01, 2) for c in closes]
        lows = [round(c * 0.99, 2) for c in closes]
        lookup[stock_id] = {"close": closes, "high": highs, "low": lows}
    return lookup


UNIVERSE = ["0050", "2330", "2454", "3711", "3231", "2382", "6669", "2882", "2881", "2891"]
SECTORS = [
    {"sector": "半導體", "representative_stocks": ["2330", "2454", "3711"]},
    {"sector": "AI", "representative_stocks": ["3231", "2382", "6669"]},
    {"sector": "金融", "representative_stocks": ["2882", "2881", "2891"]},
]


@pytest.fixture
def tmp_repo(monkeypatch):
    d = Path(tempfile.mkdtemp())
    monkeypatch.setattr(pipeline, "REPORTS_DIR", d / "reports")
    monkeypatch.setattr(pipeline, "PUBLIC_REPORTS_DIR", d / "reports_public")
    monkeypatch.setattr(pipeline, "REPO_ROOT", d)
    monkeypatch.setattr(pipeline, "STRATEGIES_DIR", Path(__file__).resolve().parent.parent / "strategies")
    monkeypatch.delenv("STATE_REPO_TOKEN", raising=False)

    holdings_a = d / "holdings_a.json"
    holdings_a.write_text(
        json.dumps({"cash": 50000, "holdings": [{"stock_id": "2330", "name": "台積電", "shares": 100, "cost_basis": 90.0}], "new_cash_inflow_today": False}),
        encoding="utf-8",
    )
    holdings_b = d / "holdings_b.json"
    holdings_b.write_text(
        json.dumps({"cash": 20000, "holdings": [{"stock_id": "2317", "name": "鴻海", "shares": 100, "cost_basis": 200.0}], "new_cash_inflow_today": False}),
        encoding="utf-8",
    )

    yield d
    shutil.rmtree(d, ignore_errors=True)


def portfolio_configs():
    return [
        {"id": "portfolio_a", "holdings_file": "holdings_a.json", "strategy": "strategy_momentum.json"},
        {"id": "portfolio_b", "holdings_file": "holdings_b.json", "strategy": "strategy_meanreversion.json"},
    ]


def test_t6_1_two_portfolios_do_not_interfere(tmp_repo):
    price_lookup = make_price_lookup()
    configs = portfolio_configs()

    succeeded, failed = run_portfolios(
        portfolio_configs=configs,
        universe_stock_ids=UNIVERSE,
        watched_sectors_config=SECTORS,
        price_lookup=price_lookup,
        pe_lookup_all={"portfolio_a": {}, "portfolio_b": {}},
        is_first_trading_day_of_month=False,
        report_date="2026-08-03",
        failed_stock_ids=[],
    )

    assert succeeded == ["portfolio_a", "portfolio_b"]
    assert failed == []

    report_a = json.loads((tmp_repo / "reports" / "portfolio_a" / "2026-08-03" / "report.json").read_text())
    report_b = json.loads((tmp_repo / "reports" / "portfolio_b" / "2026-08-03" / "report.json").read_text())

    # 各自的持股互不干擾
    assert report_a["holdings"][0]["stock_id"] == "2330"
    assert report_b["holdings"][0]["stock_id"] == "2317"
    # 套用不同策略，前十強排名不需要相同
    assert report_a["top10"] != report_b["top10"]

    validate_report(report_a)
    validate_report(report_b)


def test_t6_1_public_reports_are_isolated_by_portfolio(tmp_repo):
    price_lookup = make_price_lookup()
    run_portfolios(
        portfolio_configs=portfolio_configs(),
        universe_stock_ids=UNIVERSE,
        watched_sectors_config=SECTORS,
        price_lookup=price_lookup,
        pe_lookup_all={"portfolio_a": {}, "portfolio_b": {}},
        is_first_trading_day_of_month=False,
        report_date="2026-08-03",
        failed_stock_ids=[],
    )

    public_a = json.loads((tmp_repo / "reports_public" / "portfolio_a" / "2026-08-03" / "report.json").read_text())
    public_b = json.loads((tmp_repo / "reports_public" / "portfolio_b" / "2026-08-03" / "report.json").read_text())
    validate_public_report(public_a)
    validate_public_report(public_b)

    index_a = json.loads((tmp_repo / "reports_public" / "portfolio_a" / "index.json").read_text())
    index_b = json.loads((tmp_repo / "reports_public" / "portfolio_b" / "index.json").read_text())
    assert index_a == ["2026-08-03"]
    assert index_b == ["2026-08-03"]


def test_t6_2_swapping_strategy_changes_next_day_ranking(tmp_repo):
    price_lookup = make_price_lookup()
    configs = [{"id": "portfolio_a", "holdings_file": "holdings_a.json", "strategy": "strategy_momentum.json"}]

    run_portfolios(
        portfolio_configs=configs,
        universe_stock_ids=UNIVERSE,
        watched_sectors_config=SECTORS,
        price_lookup=price_lookup,
        pe_lookup_all={"portfolio_a": {}},
        is_first_trading_day_of_month=True,
        report_date="2026-08-03",
        failed_stock_ids=[],
    )
    day1 = json.loads((tmp_repo / "reports_public" / "portfolio_a" / "2026-08-03" / "report.json").read_text())

    # 隔天把同一個組合換成不同策略
    configs[0]["strategy"] = "strategy_meanreversion.json"
    run_portfolios(
        portfolio_configs=configs,
        universe_stock_ids=UNIVERSE,
        watched_sectors_config=SECTORS,
        price_lookup=price_lookup,
        pe_lookup_all={"portfolio_a": {}},
        is_first_trading_day_of_month=False,
        report_date="2026-08-04",
        failed_stock_ids=[],
    )
    day2 = json.loads((tmp_repo / "reports_public" / "portfolio_a" / "2026-08-04" / "report.json").read_text())

    assert day1["top10"] != day2["top10"]
    # 兩天的報告都各自保留，不是互相覆蓋
    assert (tmp_repo / "reports_public" / "portfolio_a" / "2026-08-03" / "report.json").exists()
    assert (tmp_repo / "reports_public" / "portfolio_a" / "2026-08-04" / "report.json").exists()


def test_t6_3_one_portfolio_failure_does_not_affect_others(tmp_repo):
    price_lookup = make_price_lookup()
    configs = [
        {"id": "portfolio_a", "holdings_file": "holdings_a.json", "strategy": "strategy_momentum.json"},
        {"id": "portfolio_broken", "holdings_file": "does_not_exist.json", "strategy": "strategy_does_not_exist.json"},
        {"id": "portfolio_b", "holdings_file": "holdings_b.json", "strategy": "strategy_meanreversion.json"},
    ]

    succeeded, failed = run_portfolios(
        portfolio_configs=configs,
        universe_stock_ids=UNIVERSE,
        watched_sectors_config=SECTORS,
        price_lookup=price_lookup,
        pe_lookup_all={"portfolio_a": {}, "portfolio_broken": {}, "portfolio_b": {}},
        is_first_trading_day_of_month=False,
        report_date="2026-08-03",
        failed_stock_ids=[],
    )

    assert failed == ["portfolio_broken"]
    assert succeeded == ["portfolio_a", "portfolio_b"]

    assert (tmp_repo / "reports_public" / "portfolio_a" / "2026-08-03" / "report.json").exists()
    assert (tmp_repo / "reports_public" / "portfolio_b" / "2026-08-03" / "report.json").exists()
    assert not (tmp_repo / "reports_public" / "portfolio_broken").exists()


def test_t6_4_end_to_end_single_portfolio_pipeline(tmp_repo):
    """端到端：抓資料(模擬)→排名→預測→報告→(Dashboard 讀公開版)→(Email 讀完整版)。"""
    price_lookup = make_price_lookup()
    configs = [{"id": "default", "holdings_file": "holdings_a.json", "strategy": "strategy_momentum.json"}]

    succeeded, failed = run_portfolios(
        portfolio_configs=configs,
        universe_stock_ids=UNIVERSE,
        watched_sectors_config=SECTORS,
        price_lookup=price_lookup,
        pe_lookup_all={"default": {}},
        is_first_trading_day_of_month=False,
        report_date="2026-08-03",
        failed_stock_ids=[],
    )

    assert succeeded == ["default"] and failed == []

    # Dashboard 會讀的公開版
    public_report = json.loads((tmp_repo / "reports_public" / "2026-08-03" / "report.json").read_text())
    validate_public_report(public_report)
    assert "amount" not in public_report["cash"]

    # Email 會讀的完整版
    full_report = json.loads((tmp_repo / "reports" / "2026-08-03" / "report.json").read_text())
    validate_report(full_report)
    assert full_report["cash"]["amount"] == 50000

    from src.email_report import build_email_html

    html = build_email_html(full_report)
    assert "2330" in html


def test_load_portfolio_configs_defaults_to_single_default_without_file(tmp_repo, monkeypatch):
    monkeypatch.setattr(pipeline, "CONFIG_DIR", tmp_repo / "config_missing")
    configs = _load_portfolio_configs(cli_strategy_override="strategy_meanreversion.json")
    assert configs == [
        {"id": "default", "holdings_file": "config/holdings.json", "strategy": "strategy_meanreversion.json"}
    ]


def test_load_portfolio_configs_reads_file_and_applies_cli_override_to_default(tmp_repo, monkeypatch):
    config_dir = tmp_repo / "config"
    config_dir.mkdir()
    (config_dir / "portfolios.json").write_text(
        json.dumps(
            {
                "portfolios": [
                    {"id": "default", "holdings_file": "config/holdings.json", "strategy": "strategy_momentum.json"},
                    {"id": "other", "holdings_file": "config/holdings_other.json", "strategy": "strategy_meanreversion.json"},
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(pipeline, "CONFIG_DIR", config_dir)

    configs = _load_portfolio_configs(cli_strategy_override="strategy_meanreversion.json")
    by_id = {c["id"]: c for c in configs}
    assert by_id["default"]["strategy"] == "strategy_meanreversion.json"  # CLI 覆蓋只影響 default
    assert by_id["other"]["strategy"] == "strategy_meanreversion.json"  # 本來就是這個策略，未被動到


def test_portfolio_paths_default_matches_legacy_flat_layout(tmp_repo):
    paths = PortfolioPaths("default")
    assert paths.reports_dir == pipeline.REPORTS_DIR
    assert paths.public_reports_dir == pipeline.PUBLIC_REPORTS_DIR
    assert paths.state_repo_path == pipeline.STATE_REPO_PATH


def test_portfolio_paths_non_default_uses_subdirectory(tmp_repo):
    paths = PortfolioPaths("example_meanreversion")
    assert paths.reports_dir == pipeline.REPORTS_DIR / "example_meanreversion"
    assert paths.public_reports_dir == pipeline.PUBLIC_REPORTS_DIR / "example_meanreversion"
    assert paths.state_repo_path == "example_meanreversion/nav_state.json"
