import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.sectors import build_watched_sectors


def test_build_watched_sectors_averages_representative_stocks():
    sector_configs = [
        {"sector": "半導體", "representative_stocks": ["2330", "2454"]},
        {"sector": "AI", "representative_stocks": ["3231"]},
        {"sector": "金融", "representative_stocks": ["2882", "2881"]},
    ]
    price_data = {
        "2330": [100.0, 102.0],  # +2%
        "2454": [200.0, 198.0],  # -1%
        "3231": [50.0, 51.0],  # +2%
        "2882": [40.0, 40.0],  # 0%
        "2881": [60.0, 61.2],  # +2%
    }
    result = build_watched_sectors(sector_configs, price_data)

    semi = next(r for r in result if r["sector"] == "半導體")
    assert math.isclose(semi["today_pct_change"], (0.02 + (-0.01)) / 2, rel_tol=1e-9)

    ai = next(r for r in result if r["sector"] == "AI")
    assert math.isclose(ai["today_pct_change"], 0.02, rel_tol=1e-9)

    fin = next(r for r in result if r["sector"] == "金融")
    assert math.isclose(fin["today_pct_change"], (0.0 + 0.02) / 2, rel_tol=1e-9)


def test_build_watched_sectors_missing_data_does_not_crash():
    sector_configs = [{"sector": "半導體", "representative_stocks": ["2330", "MISSING"]}]
    price_data = {"2330": [100.0, 101.0]}
    result = build_watched_sectors(sector_configs, price_data)
    assert result[0]["today_pct_change"] is not None


def test_build_watched_sectors_all_missing_returns_none():
    sector_configs = [{"sector": "半導體", "representative_stocks": ["MISSING"]}]
    result = build_watched_sectors(sector_configs, price_data={})
    assert result[0]["today_pct_change"] is None
