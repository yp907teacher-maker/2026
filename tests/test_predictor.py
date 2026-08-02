"""次日預測模組測試，對應 Phase 2 測試案例 T2-1、T2-2、T2-3。"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.predictor import predict_next_day, walk_forward_backtest


def _wave(i: int, period: int, amplitude: float) -> float:
    half = period / 2
    phase = i % period
    if phase <= half:
        return -amplitude + (2 * amplitude / half) * phase
    return amplitude - (2 * amplitude / half) * (phase - half)


def build_daily_scores(days: int = 70, n_stocks: int = 15) -> list[dict]:
    """產生確定性（非隨機）的每日排名分數快照，模擬 strategy_engine.rank_stocks() 的輸出。"""
    history = []
    for t in range(days):
        day: dict[str, dict] = {}
        for s in range(n_stocks):
            stock_id = f"S{s:02d}"
            trend = (s - n_stocks / 2) * 0.02  # 不同股票有不同的長期趨勢方向
            score = trend * t + _wave(t + s, period=10, amplitude=1.5)
            day[stock_id] = {"score": round(score, 4)}
        history.append(day)
    return history


def test_t2_2_confidence_within_valid_range():
    history = build_daily_scores(days=20, n_stocks=15)
    predictions = predict_next_day(history, lookback=5, top_n=10)

    assert len(predictions) == 10
    for p in predictions:
        assert 0 <= p["confidence"] <= 100
        assert "predicted_score" in p
        assert "basis" in p
        assert p["basis"]["lookback_days"] >= 2


def test_predict_next_day_ranks_by_predicted_score_desc():
    history = build_daily_scores(days=20, n_stocks=15)
    predictions = predict_next_day(history, lookback=5, top_n=10)

    scores = [p["predicted_score"] for p in predictions]
    assert scores == sorted(scores, reverse=True)


def test_predict_next_day_empty_history_does_not_crash():
    assert predict_next_day([], lookback=5, top_n=10) == []
    assert predict_next_day([{"S00": {"score": 1.0}}], lookback=5, top_n=10) == []


def test_t2_1_walk_forward_backtest_produces_trackable_records():
    history = build_daily_scores(days=70, n_stocks=15)
    result = walk_forward_backtest(history, lookback=5, top_n=10)

    assert result["days_evaluated"] == 70 - 5
    assert len(result["records"]) == result["days_evaluated"]
    assert 0 <= result["avg_overlap_rate"] <= 1

    for record in result["records"]:
        assert 0 <= record["overlap_rate"] <= 1
        assert record["overlap_count"] == len(
            set(record["predicted"]) & set(record["actual"])
        )
        assert len(record["actual"]) <= 10


def test_t2_1_backtest_reproducible():
    history = build_daily_scores(days=70, n_stocks=15)
    first = walk_forward_backtest(history, lookback=5, top_n=10)
    second = walk_forward_backtest(history, lookback=5, top_n=10)
    assert first == second


def test_t2_3_prediction_output_is_json_serializable():
    history = build_daily_scores(days=20, n_stocks=15)
    predictions = predict_next_day(history, lookback=5, top_n=10)

    serialized = json.dumps(predictions, ensure_ascii=False)
    restored = json.loads(serialized)
    assert restored == predictions

    for p in restored:
        assert set(p.keys()) == {"stock_id", "predicted_score", "confidence", "basis"}


def test_t2_3_backtest_output_is_json_serializable():
    history = build_daily_scores(days=70, n_stocks=15)
    result = walk_forward_backtest(history, lookback=5, top_n=10)

    serialized = json.dumps(result, ensure_ascii=False)
    restored = json.loads(serialized)
    assert restored == result
