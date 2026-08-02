"""每日整合腳本：把 Phase 0～3 各自完成的模組串起來，產生當天的 report.json。

流程：抓行情（FinMind）→ 策略排名 → 累積排名分數歷史 → 次日預測 →
持股快照 → 關注類股 → NAV/回撤 → 再平衡判定 → 組裝並儲存 report.json。

`run_pipeline()` 是純函式（不碰檔案／網路），所有狀態經參數傳入、回傳更新後的
狀態，方便測試；`main()` 負責讀設定檔、呼叫 FinMind、寫檔案，是唯一需要真實
網路連線才能跑的部分。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.nav import append_nav_history, compute_nav_entry
from src.portfolio import build_portfolio_snapshot
from src.predictor import predict_next_day
from src.rebalance import check_rebalance
from src.report_builder import build_report, load_report, save_report
from src.score_history import append_score_snapshot, save_score_history, to_predictor_input
from src.sectors import build_watched_sectors
from src.strategy_engine import rank_stocks

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = REPO_ROOT / "config"
STRATEGIES_DIR = REPO_ROOT / "strategies"
REPORTS_DIR = REPO_ROOT / "reports"
NAV_STATE_PATH = REPORTS_DIR / "nav_state.json"
REBALANCE_STATE_PATH = REPORTS_DIR / "rebalance_state.json"
SCORE_HISTORY_PATH = REPORTS_DIR / "score_history.json"

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
) -> dict:
    """組裝當天完整的 pipeline 結果，純函式、不做任何 I/O。

    price_lookup：{stock_id: {"close":[...], "high":[...]?, "low":[...]?}}，
    只需含有資料的股票，缺資料的股票在下游各模組都會被優雅地排除，不拋例外。

    回傳 {"report", "score_history", "nav_state", "rebalance_state"}，
    呼叫端負責把這四樣分別寫入對應檔案。
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

    report = build_report(
        date=report_date,
        portfolio_snapshot=portfolio_snapshot,
        top10=top10,
        predictions=predictions,
        watched_sectors=watched_sectors,
        nav_history=nav_history,
    )
    report["rebalance"] = {"triggered": triggered, "reason": reason}

    return {
        "report": report,
        "score_history": new_score_history,
        "nav_state": new_nav_state,
        "rebalance_state": new_rebalance_state,
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


def _fetch_price_lookup(client, stock_ids: list[str], start_date: str, end_date: str) -> dict:
    """向 FinMind 逐檔抓日 K，失敗的股票印出錯誤並跳過，不中斷整批流程。"""
    price_lookup: dict[str, dict] = {}
    dates_by_stock: dict[str, list[str]] = {}

    for stock_id in stock_ids:
        result = client.get_daily_price(stock_id, start_date, end_date)
        if not result.ok or not result.data:
            print(f"[warn] 抓取 {stock_id} 價格失敗，略過: {result.error}")
            continue

        closes = [row["close"] for row in result.data]
        highs = [row["max"] for row in result.data]
        lows = [row["min"] for row in result.data]
        dates = [row["date"] for row in result.data]

        price_lookup[stock_id] = {"close": closes, "high": highs, "low": lows}
        dates_by_stock[stock_id] = dates

    return price_lookup, dates_by_stock


def _fetch_pe_lookup(client, stock_ids: list[str], start_date: str, end_date: str) -> dict:
    pe_lookup: dict[str, float] = {}
    for stock_id in stock_ids:
        result = client.get_per_pbr(stock_id, start_date, end_date)
        if result.ok and result.data:
            latest = result.data[-1]
            if isinstance(latest.get("PER"), (int, float)):
                pe_lookup[stock_id] = latest["PER"]
    return pe_lookup


def main() -> int:
    from datetime import date, timedelta

    from src.data_sources.finmind import FinMindClient

    universe_config = _load_json(CONFIG_DIR / "universe.json", {"stock_ids": []})
    holdings_config = _load_json(CONFIG_DIR / "holdings.json", {"cash": 0, "holdings": []})
    watched_sectors_config = _load_json(CONFIG_DIR / "watched_sectors.json", {"sectors": []})

    strategy_name = sys.argv[1] if len(sys.argv) > 1 else "strategy_momentum.json"
    with open(STRATEGIES_DIR / strategy_name, encoding="utf-8") as fh:
        strategy = json.load(fh)

    universe_stock_ids = universe_config["stock_ids"]
    holding_ids = [h["stock_id"] for h in holdings_config.get("holdings", [])]
    sector_ids = [
        sid
        for sector in watched_sectors_config.get("sectors", [])
        for sid in sector["representative_stocks"]
    ]
    all_stock_ids = sorted(set(universe_stock_ids) | set(holding_ids) | set(sector_ids))

    end_date = date.today().isoformat()
    start_date = (date.today() - timedelta(days=400)).isoformat()

    client = FinMindClient()
    price_lookup, dates_by_stock = _fetch_price_lookup(client, all_stock_ids, start_date, end_date)
    pe_lookup = _fetch_pe_lookup(client, holding_ids, start_date, end_date)

    if "0050" not in dates_by_stock:
        print("[error] 無法取得 0050 的交易日曆（benchmark 股票抓取失敗），中止本次執行")
        return 1

    calendar_dates = dates_by_stock["0050"]
    report_date = calendar_dates[-1]
    is_first_trading_day_of_month = (
        len(calendar_dates) >= 2 and calendar_dates[-1][:7] != calendar_dates[-2][:7]
    )

    previous_report = None
    existing_report_dates = sorted(
        p.name for p in REPORTS_DIR.iterdir() if p.is_dir() and p.name < report_date
    ) if REPORTS_DIR.exists() else []
    if existing_report_dates:
        previous_report = load_report(existing_report_dates[-1], base_dir=REPORTS_DIR)

    score_history = _load_json(SCORE_HISTORY_PATH, [])
    nav_state = _load_json(NAV_STATE_PATH, None)
    rebalance_state = _load_json(REBALANCE_STATE_PATH, None)

    result = run_pipeline(
        report_date=report_date,
        is_first_trading_day_of_month=is_first_trading_day_of_month,
        universe_stock_ids=universe_stock_ids,
        holdings_config=holdings_config,
        watched_sectors_config=watched_sectors_config.get("sectors", []),
        strategy=strategy,
        price_lookup=price_lookup,
        pe_lookup=pe_lookup,
        previous_report=previous_report,
        score_history=score_history,
        nav_state=nav_state,
        rebalance_state=rebalance_state,
    )

    save_report(result["report"], base_dir=REPORTS_DIR)
    save_score_history(result["score_history"], SCORE_HISTORY_PATH)
    _save_json(NAV_STATE_PATH, result["nav_state"])
    _save_json(REBALANCE_STATE_PATH, result["rebalance_state"])

    print(f"report.json 已產生：reports/{report_date}/report.json")
    print(f"再平衡：{result['report']['rebalance']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
