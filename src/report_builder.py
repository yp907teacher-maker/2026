"""組裝並儲存每日 report.json（Model），對應計劃書第 6 節 Model/View 分離設計。

report.json 是純資料，不含任何 HTML/樣式；Dashboard 與 Email 各自讀同一份檔案
渲染成自己的 View，兩者邏輯互相獨立。

完整版（含現金金額、股數、成本、市值等絕對金額）只應存在本機／私人環境，
`REPORTS_DIR` 預期被 .gitignore 排除。公開 repo／GitHub Pages Dashboard 要讀的
是 `build_public_report()` 產生、拿掉絕對金額欄位的版本，存在 `PUBLIC_REPORTS_DIR`
（會被 commit 進 git）。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .report_schema import build_public_report, validate_report

REPO_ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = REPO_ROOT / "reports"
PUBLIC_REPORTS_DIR = REPO_ROOT / "reports_public"


def build_report(
    date: str,
    portfolio_snapshot: dict,
    top10: list[dict],
    predictions: dict,
    watched_sectors: list[dict],
    nav_history: list[dict],
    generated_at: str | None = None,
) -> dict:
    """組裝完整版 report.json 內容（純 dict，尚未寫檔），含真實金額，僅供私人使用。"""
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
    """寫入 reports/YYYY-MM-DD/report.json（完整版，含真實金額）；同一天重複儲存
    視為覆蓋當天報告（對應 T3-2：連續多天執行時，各自日期資料夾互不覆蓋彼此）。
    這個目錄預期不進 git，只在本機／私人環境保存。"""
    path = report_path(report["date"], base_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
    return path


def load_report(date: str, base_dir: Path | str | None = None) -> dict:
    path = report_path(date, base_dir)
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def public_report_path(date: str, base_dir: Path | str | None = None) -> Path:
    base = Path(base_dir) if base_dir is not None else PUBLIC_REPORTS_DIR
    return base / date / "report.json"


def save_public_report(report: dict, base_dir: Path | str | None = None) -> Path:
    """把完整版 report 去敏感化後，寫入 reports_public/YYYY-MM-DD/report.json
    （可安全進公開 repo，供 GitHub Pages Dashboard 讀取）。"""
    public_report = build_public_report(report)
    path = public_report_path(public_report["date"], base_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(public_report, fh, ensure_ascii=False, indent=2)
    return path


def load_public_report(date: str, base_dir: Path | str | None = None) -> dict:
    path = public_report_path(date, base_dir)
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)
