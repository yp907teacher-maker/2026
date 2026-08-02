"""追蹤組合 NAV（淨值）與回撤序列計算。

NAV 以第一次執行當天的總資產為基準（NAV=1.0），之後每天用當日總資產除以基準
換算；回撤 = (NAV - 歷史最高 NAV) / 歷史最高 NAV，恆為 <= 0。狀態（基準值、
歷史最高 NAV）需跨日保存，由呼叫端負責讀寫（見 scripts/daily_pipeline.py）。
"""

from __future__ import annotations


def compute_nav_entry(date: str, total_value: float, state: dict | None) -> tuple[dict, dict]:
    """回傳 (今日 nav_history 條目, 更新後狀態)。

    state 為 None 或缺少 baseline 時，視為第一次執行，以今日 total_value 為基準
    （NAV 從 1.0 開始）。
    """
    state = dict(state) if state else {}
    baseline = state.get("baseline_total_value")
    peak_nav = state.get("peak_nav", 1.0)

    if not baseline:
        baseline = total_value

    nav = total_value / baseline if baseline else 1.0
    peak_nav = max(peak_nav, nav)
    drawdown_pct = (nav - peak_nav) / peak_nav if peak_nav else 0.0

    new_state = {"baseline_total_value": baseline, "peak_nav": peak_nav}
    entry = {"date": date, "nav": nav, "drawdown_pct": drawdown_pct}
    return entry, new_state


def append_nav_history(
    previous_history: list[dict], entry: dict, max_days: int = 400
) -> list[dict]:
    """把今日 entry 接到既有歷史後面；同一天重複執行會取代（不重複累加）。"""
    history = [h for h in previous_history if h["date"] != entry["date"]]
    history.append(entry)
    history.sort(key=lambda h: h["date"])
    return history[-max_days:]
