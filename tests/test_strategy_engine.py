"""策略引擎測試，對應 Phase 1 測試案例 T1-2、T1-3、T1-4。"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.strategy_engine import evaluate_stock, rank_stocks

REPO_ROOT = Path(__file__).resolve().parent.parent
STRATEGIES_DIR = REPO_ROOT / "strategies"


def load_strategy(filename: str) -> dict:
    with open(STRATEGIES_DIR / filename, encoding="utf-8") as fh:
        return json.load(fh)


def _triangle_wave(i: int, period: int = 10, amplitude: float = 2.0) -> float:
    """確定性三角波，疊加在趨勢上，讓序列有真實的漲跌交替（避免 RSI 卡在極值）。"""
    half = period / 2
    phase = (i % period)
    if phase <= half:
        return -amplitude + (2 * amplitude / half) * phase
    return amplitude - (2 * amplitude / half) * (phase - half)


def make_price_series(n: int, start: float, daily_change: float, noise_seed: int = 0) -> dict:
    """產生確定性（非隨機）的價格序列，方便測試可重現性；含真實漲跌交替而非單調直線。"""
    close = []
    for i in range(n):
        price = start + daily_change * i + _triangle_wave(i + noise_seed)
        close.append(round(max(price, 1.0), 2))
    high = [round(c * 1.01, 2) for c in close]
    low = [round(c * 0.99, 2) for c in close]
    volume = [1_000_000 for _ in close]
    return {"close": close, "high": high, "low": low, "volume": volume}


def build_universe() -> dict[str, dict]:
    return {
        "UP_STRONG": make_price_series(300, start=100, daily_change=0.30, noise_seed=1),
        "UP_WEAK": make_price_series(300, start=100, daily_change=0.05, noise_seed=2),
        "DOWN": make_price_series(300, start=200, daily_change=-0.30, noise_seed=3),
        "FLAT": make_price_series(300, start=100, daily_change=0.0, noise_seed=4),
    }


def test_t1_2_swapping_strategy_json_changes_ranking():
    universe = build_universe()

    momentum_strategy = load_strategy("strategy_momentum.json")
    momentum_ranked = rank_stocks(universe, momentum_strategy)
    momentum_order = [row["stock_id"] for row in momentum_ranked]

    meanrev_strategy = load_strategy("strategy_meanreversion.json")
    meanrev_ranked = rank_stocks(universe, meanrev_strategy)
    meanrev_order = [row["stock_id"] for row in meanrev_ranked]

    # 動能策略應偏好持續上漲的股票，均值回歸策略應偏好下跌/超賣的股票，
    # 兩者排名結果不應相同，證明「換策略 JSON 不用改程式碼」且結果確實隨之改變
    assert momentum_order != meanrev_order
    assert "UP_STRONG" in momentum_order
    assert momentum_order[0] == "UP_STRONG"


def test_t1_3_new_listing_excluded_without_crash():
    strategy = load_strategy("strategy_momentum.json")
    universe = build_universe()
    universe["NEW_IPO"] = make_price_series(30, start=50, daily_change=0.5)  # 上市未滿 260 日

    ranked = rank_stocks(universe, strategy)
    ranked_ids = [row["stock_id"] for row in ranked]
    assert "NEW_IPO" not in ranked_ids


def test_t1_3_missing_high_low_excluded_without_crash():
    strategy = load_strategy("strategy_meanreversion.json")  # 用到 BBANDS，不需 high/low，改用需要 high/low 的情境
    universe = build_universe()

    halted = make_price_series(300, start=80, daily_change=-0.1)
    del halted["high"]
    del halted["low"]
    universe["HALTED_NO_HL"] = halted

    strategy_with_atr = json.loads(json.dumps(strategy))
    strategy_with_atr["indicators"].append({"name": "atr14", "type": "ATR", "period": 14})
    strategy_with_atr["filters"].append({"expression": "atr14 > 0"})

    ranked = rank_stocks(universe, strategy_with_atr)
    ranked_ids = [row["stock_id"] for row in ranked]
    assert "HALTED_NO_HL" not in ranked_ids


def test_t1_3_empty_universe_does_not_crash():
    strategy = load_strategy("strategy_momentum.json")
    assert rank_stocks({}, strategy) == []


def test_t1_4_reproducible_ranking():
    strategy = load_strategy("strategy_momentum.json")
    universe = build_universe()

    first_run = rank_stocks(universe, strategy)
    second_run = rank_stocks(universe, strategy)

    assert first_run == second_run


def test_evaluate_stock_returns_none_below_history_threshold():
    strategy = load_strategy("strategy_momentum.json")
    short_series = make_price_series(50, start=100, daily_change=0.1)
    assert evaluate_stock(short_series, strategy) is None
