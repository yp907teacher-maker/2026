"""從富邦 API 查詢實際庫存，自動同步股數到 config/holdings.json。

富邦 `sdk.accounting.inventories()` 只回傳庫存股數（整股 + 零股），**不含買進
成本**，所以這支腳本只更新 `shares`，不動 `cost_basis`／`name`：
    - 既有持股：股數更新為 API 查到的真實股數，成本價/名稱保留你原本填的值
    - API 查到但清單裡沒有的新股票：加入清單，成本價留 None，需要你自己補
      （可參考 scripts/convert_holdings_csv.py 從交易紀錄回推）
    - 清單裡有但 API 查到股數為 0（已出清）的：自動移除

用法（僅限本機、需要富邦 API 憑證已設定好）：
    py -3.12 scripts/sync_holdings_from_fubon.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

CONFIG_PATH = REPO_ROOT / "config" / "holdings.json"


def extract_share_counts(inventories: list) -> dict[str, float]:
    """把富邦 Inventory 物件清單整理成 {stock_no: 總股數}（整股 today_qty ＋
    零股 odd.today_qty），股數為 0（已出清）的不列入。

    用 today_qty 而非 lastday_qty，反映含當日已成交結果的最新庫存。
    """
    totals: dict[str, float] = {}
    for inv in inventories:
        shares = inv.today_qty + inv.odd.today_qty
        if shares > 0:
            totals[inv.stock_no] = totals.get(inv.stock_no, 0) + shares
    return totals


def merge_holdings(
    existing_holdings: list[dict], live_shares: dict[str, float]
) -> tuple[list[dict], list[str], list[str]]:
    """回傳 (合併後的 holdings 清單, 新增的股票代號, 已出清移除的股票代號)。

    不會覆蓋既有的 cost_basis／name，避免把你手動維護的成本價洗掉。
    """
    existing_by_id = {h["stock_id"]: h for h in existing_holdings}

    merged = []
    added = []
    for stock_id, shares in sorted(live_shares.items()):
        if stock_id in existing_by_id:
            holding = dict(existing_by_id[stock_id])
            holding["shares"] = shares
            merged.append(holding)
        else:
            merged.append(
                {"stock_id": stock_id, "name": stock_id, "shares": shares, "cost_basis": None}
            )
            added.append(stock_id)

    removed = [sid for sid in existing_by_id if sid not in live_shares]
    return merged, added, removed


def load_config(path: Path = CONFIG_PATH) -> dict:
    if not path.exists():
        return {"cash": 0, "holdings": [], "new_cash_inflow_today": False}
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def save_config(config: dict, path: Path = CONFIG_PATH) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(config, fh, ensure_ascii=False, indent=2)


def main() -> int:
    from fubon_client import FubonClient

    client = FubonClient()
    client.connect()
    try:
        inventories = client.get_holdings()
    finally:
        client.disconnect()

    live_shares = extract_share_counts(inventories)
    config = load_config()

    merged, added, removed = merge_holdings(config.get("holdings", []), live_shares)
    config["holdings"] = merged
    save_config(config)

    print(f"已同步 {len(merged)} 檔持股的股數到 {CONFIG_PATH}")
    if added:
        print(f"新增 {len(added)} 檔（成本價留空，需要你自己在 config/holdings.json 補上 cost_basis 與 name）：{', '.join(added)}")
    if removed:
        print(f"已移除 {len(removed)} 檔（目前庫存為 0）：{', '.join(removed)}")
    print("提醒：cash（交割戶餘額）本腳本不會自動更新，仍需你自己維護。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
