"""富邦庫存同步邏輯測試。用簡單的假物件模擬 fubon_neo 的 Inventory/InventoryOdd
結構（同名屬性），不需要真的安裝 fubon_neo（那套件是 Windows-only wheel，
這個雲端 sandbox 裝不了）。
"""

import shutil
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.sync_holdings_from_fubon import extract_share_counts, load_config, merge_holdings, save_config


def make_inventory(stock_no: str, today_qty: int = 0, odd_today_qty: int = 0):
    return SimpleNamespace(
        stock_no=stock_no,
        today_qty=today_qty,
        odd=SimpleNamespace(today_qty=odd_today_qty),
    )


def test_extract_share_counts_sums_round_lot_and_odd_lot():
    inventories = [
        make_inventory("2330", today_qty=0, odd_today_qty=4),
        make_inventory("009816", today_qty=1000, odd_today_qty=0),
    ]
    result = extract_share_counts(inventories)
    assert result == {"2330": 4, "009816": 1000}


def test_extract_share_counts_skips_zero_holdings():
    inventories = [make_inventory("2330", today_qty=0, odd_today_qty=0)]
    assert extract_share_counts(inventories) == {}


def test_extract_share_counts_matches_real_fubon_sample():
    # 對應使用者實際貼出的富邦 API 回應（0050 屬於零股，009816 屬於整股）
    inventories = [
        make_inventory("0050", today_qty=0, odd_today_qty=60),
        make_inventory("0052", today_qty=0, odd_today_qty=401),
        make_inventory("009816", today_qty=1000, odd_today_qty=0),
        make_inventory("2330", today_qty=0, odd_today_qty=4),
    ]
    result = extract_share_counts(inventories)
    assert result == {"0050": 60, "0052": 401, "009816": 1000, "2330": 4}


def test_merge_holdings_updates_shares_but_preserves_cost_and_name():
    existing = [{"stock_id": "2330", "name": "台積電", "shares": 3.0, "cost_basis": 1700.0}]
    live_shares = {"2330": 4.0}

    merged, added, removed = merge_holdings(existing, live_shares)

    assert merged == [{"stock_id": "2330", "name": "台積電", "shares": 4.0, "cost_basis": 1700.0}]
    assert added == []
    assert removed == []


def test_merge_holdings_does_not_add_new_stock_by_default():
    """預設不擴大追蹤範圍，帳戶裡有的其他股票不會自動塞進 holdings.json。"""
    merged, added, removed = merge_holdings([], {"2317": 15.0})

    assert merged == []
    assert added == []
    assert removed == []


def test_merge_holdings_adds_new_stock_with_null_cost_basis_when_opted_in():
    merged, added, removed = merge_holdings([], {"2317": 15.0}, include_new=True)

    assert merged == [{"stock_id": "2317", "name": "2317", "shares": 15.0, "cost_basis": None}]
    assert added == ["2317"]
    assert removed == []


def test_merge_holdings_removes_fully_sold_stock():
    existing = [{"stock_id": "2330", "name": "台積電", "shares": 4.0, "cost_basis": 1700.0}]
    merged, added, removed = merge_holdings(existing, {})

    assert merged == []
    assert added == []
    assert removed == ["2330"]


def test_merge_holdings_handles_mixed_add_update_remove_when_opted_in():
    existing = [
        {"stock_id": "2330", "name": "台積電", "shares": 3.0, "cost_basis": 1700.0},
        {"stock_id": "2317", "name": "鴻海", "shares": 10.0, "cost_basis": 200.0},
    ]
    live_shares = {"2330": 4.0, "0050": 60.0}  # 2317 賣光了、0050 是新的

    merged, added, removed = merge_holdings(existing, live_shares, include_new=True)

    merged_ids = {h["stock_id"] for h in merged}
    assert merged_ids == {"2330", "0050"}
    assert added == ["0050"]
    assert removed == ["2317"]

    tsmc = next(h for h in merged if h["stock_id"] == "2330")
    assert tsmc["shares"] == 4.0
    assert tsmc["cost_basis"] == 1700.0  # 成本沒被洗掉


def test_merge_holdings_default_only_updates_tracked_stocks_ignores_rest():
    existing = [
        {"stock_id": "2330", "name": "台積電", "shares": 3.0, "cost_basis": 1700.0},
        {"stock_id": "2317", "name": "鴻海", "shares": 10.0, "cost_basis": 200.0},
    ]
    live_shares = {"2330": 4.0, "0050": 60.0}  # 2317 賣光了、0050 是帳戶裡沒被追蹤的股票

    merged, added, removed = merge_holdings(existing, live_shares, include_new=False)

    merged_ids = {h["stock_id"] for h in merged}
    assert merged_ids == {"2330"}  # 0050 不會被自動加入
    assert added == []
    assert removed == ["2317"]

    tsmc = next(h for h in merged if h["stock_id"] == "2330")
    assert tsmc["shares"] == 4.0
    assert tsmc["cost_basis"] == 1700.0  # 成本沒被洗掉


@pytest.fixture
def tmp_config_path():
    d = tempfile.mkdtemp()
    path = Path(d) / "holdings.json"
    yield path
    shutil.rmtree(d, ignore_errors=True)


def test_load_config_missing_file_returns_default(tmp_config_path):
    config = load_config(tmp_config_path)
    assert config == {"cash": 0, "holdings": [], "new_cash_inflow_today": False}


def test_save_and_load_config_round_trips(tmp_config_path):
    config = {"cash": 18349, "holdings": [{"stock_id": "2330", "name": "台積電", "shares": 4.0, "cost_basis": 1757.5}], "new_cash_inflow_today": False}
    save_config(config, tmp_config_path)
    assert load_config(tmp_config_path) == config
