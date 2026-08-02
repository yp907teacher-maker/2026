import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.nav import append_nav_history, compute_nav_entry


def test_first_run_nav_starts_at_one():
    entry, state = compute_nav_entry("2026-08-03", total_value=100000.0, state=None)
    assert entry["nav"] == 1.0
    assert entry["drawdown_pct"] == 0.0
    assert state["baseline_total_value"] == 100000.0
    assert state["peak_nav"] == 1.0


def test_nav_grows_with_total_value():
    _, state = compute_nav_entry("2026-08-03", total_value=100000.0, state=None)
    entry, state = compute_nav_entry("2026-08-04", total_value=110000.0, state=state)
    assert math.isclose(entry["nav"], 1.1)
    assert math.isclose(state["peak_nav"], 1.1)
    assert entry["drawdown_pct"] == 0.0


def test_drawdown_computed_after_peak():
    _, state = compute_nav_entry("2026-08-03", total_value=100000.0, state=None)
    _, state = compute_nav_entry("2026-08-04", total_value=120000.0, state=state)  # peak nav=1.2
    entry, state = compute_nav_entry("2026-08-05", total_value=108000.0, state=state)  # nav=1.08

    assert math.isclose(entry["nav"], 1.08)
    assert math.isclose(state["peak_nav"], 1.2)
    assert math.isclose(entry["drawdown_pct"], (1.08 - 1.2) / 1.2)
    assert entry["drawdown_pct"] < 0


def test_append_nav_history_replaces_same_day_not_duplicates():
    history = [{"date": "2026-08-03", "nav": 1.0, "drawdown_pct": 0.0}]
    updated_entry = {"date": "2026-08-03", "nav": 1.05, "drawdown_pct": 0.0}
    result = append_nav_history(history, updated_entry)

    assert len(result) == 1
    assert result[0]["nav"] == 1.05


def test_append_nav_history_keeps_chronological_order_and_trims():
    history = [{"date": f"2026-08-{d:02d}", "nav": 1.0, "drawdown_pct": 0.0} for d in range(1, 5)]
    new_entry = {"date": "2026-08-05", "nav": 1.1, "drawdown_pct": 0.0}
    result = append_nav_history(history, new_entry, max_days=3)

    assert len(result) == 3
    assert [h["date"] for h in result] == ["2026-08-03", "2026-08-04", "2026-08-05"]
