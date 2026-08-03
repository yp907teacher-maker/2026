"""每日整合腳本：把 Phase 0～3 各自完成的模組串起來，產生當天的 report.json。

流程：抓行情（FinMind）→ 策略排名 → 累積排名分數歷史 → 次日預測 →
持股快照 → 關注類股 → NAV/回撤 → 再平衡判定 → 組裝並儲存 report.json。

`run_pipeline()` 是純函式（不碰檔案／網路），所有狀態經參數傳入、回傳更新後的
狀態，方便測試；`main()` 負責讀設定檔、呼叫 FinMind、寫檔案，是唯一需要真實
網路連線才能跑的部分。
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

from src.nav import append_nav_history, compute_nav_entry
from src.portfolio import build_portfolio_snapshot
from src.predictor import predict_next_day
from src.rebalance import check_rebalance
from src.report_builder import build_report, save_public_report, save_report
from src.score_history import append_score_snapshot, save_score_history, to_predictor_input
from src.sectors import build_watched_sectors
from src.strategy_engine import rank_stocks

load_dotenv()

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = REPO_ROOT / "config"
STRATEGIES_DIR = REPO_ROOT / "strategies"
REPORTS_DIR = REPO_ROOT / "reports"  # 完整版（含真實金額），.gitignore 排除，僅本機／私人環境保存
PUBLIC_REPORTS_DIR = REPO_ROOT / "reports_public"  # 去敏感化版，會 commit 進 git 給公開 Dashboard 讀
NAV_STATE_PATH = REPORTS_DIR / "nav_state.json"
REBALANCE_STATE_PATH = REPORTS_DIR / "rebalance_state.json"
SCORE_HISTORY_PATH = REPORTS_DIR / "score_history.json"
# 大盤基準（0050）股價比值，不含私人資料，可安全 commit
BENCHMARK_NAV_STATE_PATH = REPORTS_DIR / "benchmark_nav_state.json"
PUBLIC_INDEX_PATH = PUBLIC_REPORTS_DIR / "index.json"

# nav_state.json 含真實金額基準值，本機執行時走本機檔案；設定 STATE_REPO_TOKEN
# 時（例如 GitHub Actions 排程）改存到另一個私人 repo，讓跨次執行也能正確累積
# NAV，同時不會讓金額進到公開 repo。見 src/state_sync.py。
STATE_REPO = os.environ.get("STATE_REPO", "yp907teacher-maker/2026-private-state")
STATE_REPO_PATH = "nav_state.json"

PREDICTOR_LOOKBACK = 5
PREDICTOR_TOP_N = 10
TOP10_SIZE = 10


def run_pipeline(
    report_date: str,
    is_first_trading_day_of_month: bool,
    universe_stock_ids: list[str],
    holdings_config: dict,
    watched_sectors_config: list[dict],
    strategy: dict,
    price_lookup: dict[str, dict],
    pe_lookup: dict[str, float],
    previous_report: dict | None,
    score_history: list[dict],
    nav_state: dict | None,
    rebalance_state: dict | None,
    benchmark_nav_state: dict | None = None,
    benchmark_stock_id: str = "0050",
) -> dict:
    """組裝當天完整的 pipeline 結果，純函式、不做任何 I/O。

    price_lookup：{stock_id: {"close":[...], "high":[...]?, "low":[...]?}}，
    只需含有資料的股票，缺資料的股票在下游各模組都會被優雅地排除，不拋例外。

    benchmark_nav_history 只是大盤基準（如 0050）的股價比值，不含任何私人資料，
    完整版與公開版兩邊都會保留，供 Dashboard NAV 曲線疊加對比（T4-3）。

    回傳 {"report", "score_history", "nav_state", "rebalance_state",
    "benchmark_nav_state"}，呼叫端負責把這些分別寫入對應檔案。
    """
    universe_prices = {
        sid: price_lookup[sid] for sid in universe_stock_ids if sid in price_lookup
    }
    all_scored = rank_stocks(universe_prices, strategy, apply_position_limit=False)
    top10 = [{"stock_id": row["stock_id"], "score": row["score"]} for row in all_scored[:TOP10_SIZE]]

    new_score_history = append_score_snapshot(score_history, report_date, all_scored)
    predictor_input = to_predictor_input(new_score_history)
    prediction_items = predict_next_day(
        predictor_input, lookback=PREDICTOR_LOOKBACK, top_n=PREDICTOR_TOP_N
    )
    predictions = {
        "lookback": PREDICTOR_LOOKBACK,
        "top_n": PREDICTOR_TOP_N,
        "items": prediction_items,
    }

    close_only = {sid: data["close"] for sid, data in price_lookup.items() if data.get("close")}

    portfolio_snapshot = build_portfolio_snapshot(
        cash=holdings_config.get("cash", 0),
        holdings_input=holdings_config.get("holdings", []),
        price_data=close_only,
        pe_data=pe_lookup,
    )

    watched_sectors = build_watched_sectors(watched_sectors_config, close_only)

    nav_entry, new_nav_state = compute_nav_entry(
        report_date, portfolio_snapshot["total_value"], nav_state
    )
    previous_nav_history = previous_report["nav_history"] if previous_report else []
    nav_history = append_nav_history(previous_nav_history, nav_entry)

    new_cash_inflow = bool(holdings_config.get("new_cash_inflow_today", False))
    triggered, reason, new_rebalance_state = check_rebalance(
        today=report_date,
        is_first_trading_day_of_month=is_first_trading_day_of_month,
        new_cash_inflow=new_cash_inflow,
        state=rebalance_state,
    )

    benchmark_price = None
    benchmark_data = price_lookup.get(benchmark_stock_id)
    if benchmark_data and benchmark_data.get("close"):
        benchmark_price = benchmark_data["close"][-1]

    if benchmark_price is not None:
        benchmark_entry, new_benchmark_nav_state = compute_nav_entry(
            report_date, benchmark_price, benchmark_nav_state
        )
        previous_benchmark_history = (
            previous_report.get("benchmark_nav_history", []) if previous_report else []
        )
        benchmark_nav_history = append_nav_history(previous_benchmark_history, benchmark_entry)
        benchmark_nav_history = [
            {"date": row["date"], "nav": row["nav"]} for row in benchmark_nav_history
        ]
    else:
        # benchmark_stock_id 抓取失敗時不中斷整批流程，只是這天沒有大盤對比資料
        new_benchmark_nav_state = benchmark_nav_state or {}
        benchmark_nav_history = (
            previous_report.get("benchmark_nav_history", []) if previous_report else []
        )

    report = build_report(
        date=report_date,
        portfolio_snapshot=portfolio_snapshot,
        top10=top10,
        predictions=predictions,
        watched_sectors=watched_sectors,
        nav_history=nav_history,
        benchmark_nav_history=benchmark_nav_history,
    )
    report["rebalance"] = {"triggered": triggered, "reason": reason}

    return {
        "report": report,
        "score_history": new_score_history,
        "nav_state": new_nav_state,
        "rebalance_state": new_rebalance_state,
        "benchmark_nav_state": new_benchmark_nav_state,
    }


def _load_json(path: Path, default):
    if not path.exists():
        return default
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)


class PortfolioPaths:
    """單一追蹤組合的檔案路徑。`default` 組合刻意沿用既有的扁平路徑（不加組合
    ID 子目錄），確保這次 Phase 6 改動不影響已經在 GitHub Actions 上跑的正式
    排程；其他組合則各自獨立在 `{portfolio_id}/` 子目錄底下，互不干擾（T6-1）。
    """

    def __init__(self, portfolio_id: str):
        self.portfolio_id = portfolio_id
        is_default = portfolio_id == "default"

        self.reports_dir = REPORTS_DIR if is_default else REPORTS_DIR / portfolio_id
        self.public_reports_dir = (
            PUBLIC_REPORTS_DIR if is_default else PUBLIC_REPORTS_DIR / portfolio_id
        )
        self.score_history_path = self.reports_dir / "score_history.json"
        self.nav_state_path = self.reports_dir / "nav_state.json"
        self.rebalance_state_path = self.reports_dir / "rebalance_state.json"
        self.benchmark_nav_state_path = self.reports_dir / "benchmark_nav_state.json"
        self.public_index_path = self.public_reports_dir / "index.json"
        # 私人 repo 裡的檔名；default 沿用既有的 "nav_state.json"，避免既有的
        # 私人 repo 內容被視為另一個組合的資料而找不到。
        self.state_repo_path = (
            STATE_REPO_PATH if is_default else f"{portfolio_id}/{STATE_REPO_PATH}"
        )


def _load_nav_state(paths: PortfolioPaths) -> dict | None:
    token = os.environ.get("STATE_REPO_TOKEN")
    if token:
        from src.state_sync import pull_state

        return pull_state(STATE_REPO, paths.state_repo_path, token)
    return _load_json(paths.nav_state_path, None)


def _save_nav_state(data: dict, report_date: str, paths: PortfolioPaths) -> None:
    token = os.environ.get("STATE_REPO_TOKEN")
    if token:
        from src.state_sync import push_state

        push_state(
            STATE_REPO,
            paths.state_repo_path,
            token,
            data,
            message=f"chore: update nav_state {paths.portfolio_id} {report_date}",
        )
    else:
        _save_json(paths.nav_state_path, data)


def _update_public_index(report_date: str, public_index_path: Path) -> None:
    """維護 {組合}/index.json：純靜態網站沒有後端可以列目錄，Dashboard
    要知道有哪些日期可選（T4-2），得靠這個索引檔。"""
    dates = _load_json(public_index_path, [])
    if report_date not in dates:
        dates.append(report_date)
    dates.sort()
    _save_json(public_index_path, dates)


def _save_warnings(
    report_date: str, failed_stock_ids: list[str], holding_ids: list[str], reports_dir: Path
) -> None:
    """把資料抓取失敗的股票整理成人類看得懂的訊息，寫進 {組合}/{date}/warnings.json，
    供 send_email.py 讀取後在 Email 頂端顯示「資料不完整」提醒（對應 T5-4）。
    沒有任何失敗時不建立檔案（維持乾淨，也讓 load_warnings() 自然回傳空清單）。
    """
    if not failed_stock_ids:
        return

    holding_id_set = set(holding_ids)
    warnings = []
    for stock_id in failed_stock_ids:
        if stock_id in holding_id_set:
            warnings.append(f"你的持股 {stock_id} 今日資料抓取失敗，報告中的市值/績效可能未更新")
        else:
            warnings.append(f"{stock_id} 資料抓取失敗，未列入今日排名/預測")

    path = reports_dir / report_date / "warnings.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(warnings, fh, ensure_ascii=False, indent=2)


def _fetch_price_lookup(client, stock_ids: list[str], start_date: str, end_date: str) -> dict:
    """向 FinMind 逐檔抓日 K，失敗的股票印出錯誤並跳過，不中斷整批流程。

    回傳 (price_lookup, dates_by_stock, failed_stock_ids)；failed_stock_ids 供
    T5-4 使用，讓 Email 明確標示「資料不完整」而不是悄悄漏掉某些股票。
    """
    price_lookup: dict[str, dict] = {}
    dates_by_stock: dict[str, list[str]] = {}
    failed_stock_ids: list[str] = []

    for stock_id in stock_ids:
        result = client.get_daily_price(stock_id, start_date, end_date)
        if not result.ok or not result.data:
            print(f"[warn] 抓取 {stock_id} 價格失敗，略過: {result.error}")
            failed_stock_ids.append(stock_id)
            continue

        closes = [row["close"] for row in result.data]
        highs = [row["max"] for row in result.data]
        lows = [row["min"] for row in result.data]
        dates = [row["date"] for row in result.data]

        price_lookup[stock_id] = {"close": closes, "high": highs, "low": lows}
        dates_by_stock[stock_id] = dates

    return price_lookup, dates_by_stock, failed_stock_ids


def _fetch_pe_lookup(client, stock_ids: list[str], start_date: str, end_date: str) -> dict:
    pe_lookup: dict[str, float] = {}
    for stock_id in stock_ids:
        result = client.get_per_pbr(stock_id, start_date, end_date)
        if result.ok and result.data:
            latest = result.data[-1]
            if isinstance(latest.get("PER"), (int, float)):
                pe_lookup[stock_id] = latest["PER"]
    return pe_lookup


def _load_portfolio_configs(cli_strategy_override: str | None) -> list[dict]:
    """讀 config/portfolios.json 取得追蹤組合清單；檔案不存在時退回單一
    `default` 組合（用 config/holdings.json ＋ CLI 參數指定的策略），維持
    Phase 6 之前的既有行為完全不變。
    """
    portfolios_file = CONFIG_DIR / "portfolios.json"
    if not portfolios_file.exists():
        return [
            {
                "id": "default",
                "holdings_file": "config/holdings.json",
                "strategy": cli_strategy_override or "strategy_momentum.json",
            }
        ]

    config = _load_json(portfolios_file, {"portfolios": []})
    portfolios = config.get("portfolios", [])
    if cli_strategy_override:
        for p in portfolios:
            if p["id"] == "default":
                p["strategy"] = cli_strategy_override
    return portfolios


def process_portfolio(
    portfolio_cfg: dict,
    universe_stock_ids: list[str],
    watched_sectors_config: list[dict],
    price_lookup: dict[str, dict],
    pe_lookup_all: dict[str, dict[str, float]],
    is_first_trading_day_of_month: bool,
    report_date: str,
    failed_stock_ids: list[str],
) -> dict:
    """處理單一追蹤組合的完整流程：讀設定 → 跑 run_pipeline() → 存檔。

    拋出例外交由呼叫端（main()）捕捉，確保一個組合失敗不影響其他組合（T6-3）。
    """
    portfolio_id = portfolio_cfg["id"]
    paths = PortfolioPaths(portfolio_id)

    holdings_config = _load_json(REPO_ROOT / portfolio_cfg["holdings_file"], {"cash": 0, "holdings": []})
    with open(STRATEGIES_DIR / portfolio_cfg["strategy"], encoding="utf-8") as fh:
        strategy = json.load(fh)

    holding_ids = [h["stock_id"] for h in holdings_config.get("holdings", [])]
    pe_lookup = pe_lookup_all.get(portfolio_id, {})

    previous_report = None
    existing_report_dates = (
        sorted(p.name for p in paths.public_reports_dir.iterdir() if p.is_dir() and p.name < report_date)
        if paths.public_reports_dir.exists()
        else []
    )
    if existing_report_dates:
        from src.report_builder import load_public_report

        previous_report = load_public_report(existing_report_dates[-1], base_dir=paths.public_reports_dir)

    score_history = _load_json(paths.score_history_path, [])
    nav_state = _load_nav_state(paths)
    rebalance_state = _load_json(paths.rebalance_state_path, None)
    benchmark_nav_state = _load_json(paths.benchmark_nav_state_path, None)

    result = run_pipeline(
        report_date=report_date,
        is_first_trading_day_of_month=is_first_trading_day_of_month,
        universe_stock_ids=universe_stock_ids,
        holdings_config=holdings_config,
        watched_sectors_config=watched_sectors_config,
        strategy=strategy,
        price_lookup=price_lookup,
        pe_lookup=pe_lookup,
        previous_report=previous_report,
        score_history=score_history,
        nav_state=nav_state,
        rebalance_state=rebalance_state,
        benchmark_nav_state=benchmark_nav_state,
    )

    save_report(result["report"], base_dir=paths.reports_dir)
    save_public_report(result["report"], base_dir=paths.public_reports_dir)
    save_score_history(result["score_history"], paths.score_history_path)
    _save_nav_state(result["nav_state"], report_date, paths)
    _save_json(paths.rebalance_state_path, result["rebalance_state"])
    _save_json(paths.benchmark_nav_state_path, result["benchmark_nav_state"])
    _update_public_index(report_date, paths.public_index_path)
    _save_warnings(report_date, failed_stock_ids, holding_ids, paths.reports_dir)

    return result


def run_portfolios(
    portfolio_configs: list[dict],
    universe_stock_ids: list[str],
    watched_sectors_config: list[dict],
    price_lookup: dict[str, dict],
    pe_lookup_all: dict[str, dict[str, float]],
    is_first_trading_day_of_month: bool,
    report_date: str,
    failed_stock_ids: list[str],
) -> tuple[list[str], list[str]]:
    """依序處理所有追蹤組合，單一組合拋例外只會被記錄、跳過，不影響其餘組合
    （T6-3：錯誤隔離）。回傳 (成功的組合 id 清單, 失敗的組合 id 清單)。
    """
    succeeded: list[str] = []
    failed: list[str] = []

    for portfolio_cfg in portfolio_configs:
        portfolio_id = portfolio_cfg["id"]
        try:
            result = process_portfolio(
                portfolio_cfg=portfolio_cfg,
                universe_stock_ids=universe_stock_ids,
                watched_sectors_config=watched_sectors_config,
                price_lookup=price_lookup,
                pe_lookup_all=pe_lookup_all,
                is_first_trading_day_of_month=is_first_trading_day_of_month,
                report_date=report_date,
                failed_stock_ids=failed_stock_ids,
            )
        except Exception as exc:  # noqa: BLE001 - 單一組合失敗不能讓其他組合連帶失敗
            print(f"[error] 組合「{portfolio_id}」執行失敗，跳過（不影響其他組合）：{exc!r}")
            failed.append(portfolio_id)
            continue

        succeeded.append(portfolio_id)
        paths = PortfolioPaths(portfolio_id)
        print(f"[ok] 組合「{portfolio_id}」完整版已產生：{paths.reports_dir}/{report_date}/report.json")
        print(f"[ok] 組合「{portfolio_id}」公開版已產生：{paths.public_reports_dir}/{report_date}/report.json")
        print(f"[ok] 組合「{portfolio_id}」再平衡：{result['report']['rebalance']}")

    return succeeded, failed


def main() -> int:
    from datetime import date, timedelta

    from src.data_sources.finmind import FinMindClient

    universe_config = _load_json(CONFIG_DIR / "universe.json", {"stock_ids": []})
    watched_sectors_config = _load_json(CONFIG_DIR / "watched_sectors.json", {"sectors": []})
    sectors_list = watched_sectors_config.get("sectors", [])

    cli_strategy_override = sys.argv[1] if len(sys.argv) > 1 else None
    portfolio_configs = _load_portfolio_configs(cli_strategy_override)

    universe_stock_ids = universe_config["stock_ids"]
    sector_ids = [sid for sector in sectors_list for sid in sector["representative_stocks"]]

    # 每個組合各自的持股，先讀出來湊成一次性抓取的股票清單，避免對同一檔股票
    # 重複打 FinMind API（多組合共用同一批行情資料，只有持股/策略不同）。
    holdings_by_portfolio: dict[str, list[str]] = {}
    for p in portfolio_configs:
        cfg = _load_json(REPO_ROOT / p["holdings_file"], {"holdings": []})
        holdings_by_portfolio[p["id"]] = [h["stock_id"] for h in cfg.get("holdings", [])]

    all_holding_ids = sorted({sid for ids in holdings_by_portfolio.values() for sid in ids})
    all_stock_ids = sorted(set(universe_stock_ids) | set(all_holding_ids) | set(sector_ids))

    end_date = date.today().isoformat()
    start_date = (date.today() - timedelta(days=400)).isoformat()

    client = FinMindClient()
    price_lookup, dates_by_stock, failed_stock_ids = _fetch_price_lookup(
        client, all_stock_ids, start_date, end_date
    )

    pe_lookup_all: dict[str, dict[str, float]] = {}
    for portfolio_id, holding_ids in holdings_by_portfolio.items():
        pe_lookup_all[portfolio_id] = _fetch_pe_lookup(client, holding_ids, start_date, end_date)

    if "0050" not in dates_by_stock:
        print("[error] 無法取得 0050 的交易日曆（benchmark 股票抓取失敗），中止本次執行")
        return 1

    calendar_dates = dates_by_stock["0050"]
    report_date = calendar_dates[-1]
    is_first_trading_day_of_month = (
        len(calendar_dates) >= 2 and calendar_dates[-1][:7] != calendar_dates[-2][:7]
    )

    succeeded, failed = run_portfolios(
        portfolio_configs=portfolio_configs,
        universe_stock_ids=universe_stock_ids,
        watched_sectors_config=sectors_list,
        price_lookup=price_lookup,
        pe_lookup_all=pe_lookup_all,
        is_first_trading_day_of_month=is_first_trading_day_of_month,
        report_date=report_date,
        failed_stock_ids=failed_stock_ids,
    )

    print(f"\n共 {len(portfolio_configs)} 個組合，成功 {len(succeeded)} 個，失敗 {len(failed)} 個")
    if failed:
        print(f"失敗的組合：{', '.join(failed)}")

    return 0 if succeeded else 1


if __name__ == "__main__":
    sys.exit(main())
