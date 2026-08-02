"""排名分數的每日快照儲存，累積成 predictor.py 所需的多日歷史。

strategy_engine.rank_stocks() 每次只回傳當天的排名，本模組負責把每天的結果
存成一個滾動視窗檔案（reports/score_history.json），供 predictor 使用。
"""

from __future__ import annotations

import json
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "reports" / "score_history.json"


def load_score_history(path: Path | str = DEFAULT_PATH) -> list[dict]:
    """讀取歷史快照，檔案不存在時回傳空 list（第一次執行的正常狀況，不視為錯誤）。"""
    path = Path(path)
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def append_score_snapshot(
    history: list[dict], date: str, scored_stocks: list[dict], max_days: int = 30
) -> list[dict]:
    """把 rank_stocks(apply_position_limit=False) 的結果整理成 {stock_id: {"score":...}}
    後接到歷史後面；同一天重複執行會取代，不重複累加。只保留最近 max_days 天。
    """
    scores = {row["stock_id"]: {"score": row["score"]} for row in scored_stocks}
    filtered = [h for h in history if h["date"] != date]
    filtered.append({"date": date, "scores": scores})
    filtered.sort(key=lambda h: h["date"])
    return filtered[-max_days:]


def save_score_history(history: list[dict], path: Path | str = DEFAULT_PATH) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(history, fh, ensure_ascii=False, indent=2)


def to_predictor_input(history: list[dict]) -> list[dict]:
    """轉成 predictor.predict_next_day() / walk_forward_backtest() 需要的格式：
    依日期由舊到新排列的 list[dict[stock_id, {"score": float}]]（不含日期欄位）。
    """
    ordered = sorted(history, key=lambda h: h["date"])
    return [h["scores"] for h in ordered]
