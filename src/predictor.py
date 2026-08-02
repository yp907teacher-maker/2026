"""次日預測模組：以「排名分數延伸／動能延續」為基礎的可解釋預測模型。

設計原則（對應計劃書 Phase 2）：不是要求高準確率，而是要求「可衡量、可解釋」。
模型完全基於歷史排名分數的線性趨勢外插，任何一筆預測都可以回答
「為什麼」（basis 欄位列出依據），不使用黑箱模型。
"""

from __future__ import annotations

DailyScores = dict[str, dict]  # stock_id -> {"score": float, ...}


def predict_next_day(
    history: list[DailyScores], lookback: int = 5, top_n: int = 10
) -> list[dict]:
    """依最近 lookback 天的排名分數趨勢，預測次日分數並排序取前 top_n 檔。

    history：由舊到新排列的每日排名分數快照（通常來自 strategy_engine.rank_stocks()
    的輸出整理而成）。若某股票在窗口內出現天數不足 2 天，無法算出趨勢，直接排除。
    """
    if len(history) < 2:
        return []

    window = history[-lookback:]
    latest_day = window[-1]

    predictions: list[dict] = []
    for stock_id in sorted(latest_day):  # 排序輸入，確保同分時順序穩定、結果可重現
        scores = [day[stock_id]["score"] for day in window if stock_id in day]
        if len(scores) < 2:
            continue

        deltas = [scores[i] - scores[i - 1] for i in range(1, len(scores))]
        avg_trend = sum(deltas) / len(deltas)
        predicted_score = scores[-1] + avg_trend

        if avg_trend == 0:
            consistency = 0.0
        else:
            same_direction = sum(1 for d in deltas if (d > 0) == (avg_trend > 0))
            consistency = same_direction / len(deltas)
        confidence = round(consistency * 100, 1)

        predictions.append(
            {
                "stock_id": stock_id,
                "predicted_score": predicted_score,
                "confidence": confidence,
                "basis": {
                    "latest_score": scores[-1],
                    "avg_daily_change": avg_trend,
                    "lookback_days": len(scores),
                },
            }
        )

    predictions.sort(key=lambda p: p["predicted_score"], reverse=True)
    return predictions[:top_n]


def walk_forward_backtest(
    daily_scores: list[DailyScores], lookback: int = 5, top_n: int = 10
) -> dict:
    """逐日往前滾動：用第 t 天之前的 lookback 天資料預測第 t 天的前 top_n 名，
    與第 t 天實際排名比對重疊率，記錄每一天的結果供追蹤（對應 T2-1）。

    不要求高重疊率，只要求「有紀錄、可衡量」。
    """
    records: list[dict] = []

    for t in range(lookback, len(daily_scores)):
        history_window = daily_scores[t - lookback : t]
        predicted = predict_next_day(history_window, lookback=lookback, top_n=top_n)
        predicted_ids = {p["stock_id"] for p in predicted}

        actual_day = daily_scores[t]
        actual_top = sorted(
            actual_day.items(), key=lambda kv: kv[1]["score"], reverse=True
        )[:top_n]
        actual_ids = {stock_id for stock_id, _ in actual_top}

        overlap_ids = predicted_ids & actual_ids
        records.append(
            {
                "day_index": t,
                "predicted": sorted(predicted_ids),
                "actual": sorted(actual_ids),
                "overlap_count": len(overlap_ids),
                "overlap_rate": len(overlap_ids) / top_n if top_n else 0.0,
            }
        )

    avg_overlap_rate = (
        sum(r["overlap_rate"] for r in records) / len(records) if records else 0.0
    )

    return {
        "lookback": lookback,
        "top_n": top_n,
        "days_evaluated": len(records),
        "avg_overlap_rate": avg_overlap_rate,
        "records": records,
    }
