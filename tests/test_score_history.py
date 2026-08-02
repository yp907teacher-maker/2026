import shutil
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.score_history import (
    append_score_snapshot,
    load_score_history,
    save_score_history,
    to_predictor_input,
)


@pytest.fixture
def tmp_path_file():
    d = tempfile.mkdtemp()
    yield Path(d) / "score_history.json"
    shutil.rmtree(d, ignore_errors=True)


def test_load_score_history_missing_file_returns_empty(tmp_path_file):
    assert load_score_history(tmp_path_file) == []


def test_append_and_save_and_reload_round_trips(tmp_path_file):
    history = []
    scored = [{"stock_id": "2330", "score": 0.1}, {"stock_id": "2317", "score": 0.05}]
    history = append_score_snapshot(history, "2026-08-03", scored)
    save_score_history(history, tmp_path_file)

    reloaded = load_score_history(tmp_path_file)
    assert reloaded == history
    assert reloaded[0]["date"] == "2026-08-03"
    assert reloaded[0]["scores"]["2330"]["score"] == 0.1


def test_append_same_day_replaces_not_duplicates():
    history = append_score_snapshot([], "2026-08-03", [{"stock_id": "2330", "score": 0.1}])
    history = append_score_snapshot(
        history, "2026-08-03", [{"stock_id": "2330", "score": 0.2}]
    )
    assert len(history) == 1
    assert history[0]["scores"]["2330"]["score"] == 0.2


def test_append_trims_to_max_days():
    history = []
    for d in range(1, 10):
        history = append_score_snapshot(
            history, f"2026-08-{d:02d}", [{"stock_id": "2330", "score": d}], max_days=5
        )
    assert len(history) == 5
    assert [h["date"] for h in history] == [f"2026-08-{d:02d}" for d in range(5, 10)]


def test_to_predictor_input_matches_predictor_expected_shape():
    history = [
        {"date": "2026-08-04", "scores": {"2330": {"score": 0.2}}},
        {"date": "2026-08-03", "scores": {"2330": {"score": 0.1}}},
    ]
    result = to_predictor_input(history)
    # 應依日期排序（舊到新），不是照輸入順序
    assert result == [{"2330": {"score": 0.1}}, {"2330": {"score": 0.2}}]


def test_score_history_feeds_predictor_end_to_end():
    from src.predictor import predict_next_day

    history = []
    for d in range(1, 8):
        history = append_score_snapshot(
            history, f"2026-08-{d:02d}", [{"stock_id": "2330", "score": d * 0.1}]
        )

    predictor_input = to_predictor_input(history)
    predictions = predict_next_day(predictor_input, lookback=5, top_n=10)

    assert len(predictions) == 1
    assert predictions[0]["stock_id"] == "2330"
    assert predictions[0]["predicted_score"] > 0.7  # 持續上升趨勢，預測值應延伸超過最新分數
