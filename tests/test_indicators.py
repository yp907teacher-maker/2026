"""指標計算正確性測試（對應 T1-1：指標數值需與已知公式結果一致）。

此雲端開發環境無法連線至 TradingView/XQ 做即時人工比對，因此改以「已知範例
資料 + 公式手算/獨立實作」驗證核心算法正確性，覆蓋一般情況與邊界情況。
"""

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import indicators as ind


def test_sma_basic():
    values = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    result = ind.sma(values, 3)
    assert result[:2] == [None, None]
    assert result[2] == 2.0  # (1+2+3)/3
    assert result[9] == 9.0  # (8+9+10)/3


def test_ema_matches_hand_calculation():
    values = [10, 11, 12, 13, 14, 15]
    period = 3
    result = ind.ema(values, period)
    assert result[0] is None and result[1] is None

    seed = (10 + 11 + 12) / 3
    assert math.isclose(result[2], seed)

    multiplier = 2 / (period + 1)
    expected_3 = (values[3] - seed) * multiplier + seed
    assert math.isclose(result[3], expected_3)

    expected_4 = (values[4] - expected_3) * multiplier + expected_3
    assert math.isclose(result[4], expected_4)


def test_rsi_all_gains_is_100():
    values = [10 + i for i in range(20)]  # 連續上漲
    result = ind.rsi(values, period=14)
    assert result[14] == 100.0


def test_rsi_all_losses_is_0():
    values = [30 - i for i in range(20)]  # 連續下跌
    result = ind.rsi(values, period=14)
    assert result[14] == 0.0


def test_rsi_known_dataset_first_value():
    # StockCharts RSI 教學範例的前 15 個收盤價
    closes = [
        44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42,
        45.84, 46.08, 45.89, 46.03, 45.61, 46.28, 46.28,
    ]
    result = ind.rsi(closes, period=14)
    # 手算第 14 期（index 14）的平均漲跌：14 個變動中漲 9 次共 3.61，跌 3 次共 0.86（四捨五入至百分位）
    changes = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [max(c, 0) for c in changes]
    losses = [max(-c, 0) for c in changes]
    avg_gain = sum(gains) / 14
    avg_loss = sum(losses) / 14
    expected_rs = avg_gain / avg_loss
    expected_rsi = 100 - (100 / (1 + expected_rs))
    assert math.isclose(result[14], expected_rsi, rel_tol=1e-9)


def test_macd_line_equals_ema_difference():
    values = [10 + (i % 5) + i * 0.1 for i in range(60)]
    macd_line, signal_line, histogram = ind.macd(values, fast=12, slow=26, signal=9)

    ema_fast = ind.ema(values, 12)
    ema_slow = ind.ema(values, 26)
    for i in range(len(values)):
        if ema_fast[i] is not None and ema_slow[i] is not None:
            assert math.isclose(macd_line[i], ema_fast[i] - ema_slow[i])

    for i in range(len(values)):
        if macd_line[i] is not None and signal_line[i] is not None:
            assert math.isclose(histogram[i], macd_line[i] - signal_line[i])


def test_bollinger_bands_width_on_constant_series():
    values = [100.0] * 25
    upper, middle, lower = ind.bollinger_bands(values, period=20, num_std=2.0)
    # 價格完全不變，標準差為 0，上下軌應等於中軌
    assert math.isclose(upper[19], 100.0)
    assert math.isclose(lower[19], 100.0)
    assert math.isclose(middle[19], 100.0)


def test_atr_zero_on_flat_prices():
    n = 20
    high = [10.0] * n
    low = [10.0] * n
    close = [10.0] * n
    result = ind.atr(high, low, close, period=14)
    assert math.isclose(result[14], 0.0)


def test_adx_none_when_insufficient_data():
    values = list(range(10))
    result = ind.adx(values, values, values, period=14)
    assert all(v is None for v in result)


def test_indicators_do_not_raise_on_short_series():
    short = [1.0, 2.0]
    assert ind.sma(short, 5) == [None, None]
    assert ind.ema(short, 5) == [None, None]
    assert ind.rsi(short, 14) == [None, None]
