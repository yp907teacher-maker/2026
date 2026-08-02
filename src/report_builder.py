"""組裝並儲存每日 report.json（Model），對應計劃書第 6 節 Model/View 分離設計。

report.json 是純資料，不含任何 HTML/樣式；Dashboard 與 Email 各自讀同一份檔案
渲染成自己的 View，兩者邏輯互相獨立。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .report_schema import validate_report

REPORTS_DIR = Path(__file__).resolve().parent.parent / "reports"


def build_report(
    date: str,
    portfolio_snapshot: dict,
    top10: list[dict],
    predictions: dict,
    watched_sectors: list[dict],
    nav_history: list[dict],
    generated_at: str | None = None,
) -> dict:
    """組裝完整 report.json 內容（純 dict，尚未寫檔）。"""
    report = {
        "date": date,
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
        "cash": portfolio_snapshot["cash"],
        "holdings": portfolio_snapshot["holdings"],
        "total_market_value": portfolio_snapshot["total_market_value"],
        "total_value": portfolio_snapshot["total_value"],
        "top10": top10,
        "predictions": predictions,
        "watched_sectors": watched_sectors,
        "nav_history": nav_history,
    }
    validate_report(report)
    return report


def report_path(date: str, base_dir: Path | str | None = None) -> Path:
    base = Path(base_dir) if base_dir is not None else REPORTS_DIR
    return base / date / "report.json"


def save_report(report: dict, base_dir: Path | str | None = None) -> Path:
    """寫入 reports/YYYY-MM-DD/report.json；同一天重複儲存視為覆蓋當天報告
    （對應 T3-2：連續多天執行時，各自日期資料夾互不覆蓋彼此）。"""
    path = report_path(report["date"], base_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
    return path


def load_report(date: str, base_dir: Path | str | None = None) -> dict:
    path = report_path(date, base_dir)
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)
