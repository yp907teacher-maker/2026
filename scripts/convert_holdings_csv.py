"""把富邦證券匯出的成交紀錄 CSV，轉換成 config/holdings.json 的格式。

用法：
    python scripts/convert_holdings_csv.py <成交紀錄.csv> [--min-pct 1.0] [--out config/holdings.json]

輸入 CSV 為富邦「成交紀錄」匯出檔（Big5 編碼），欄位：
    成交日期,交易類別,股票名稱,成交股數,成交單價,成交價金,手續費,交易稅,...,淨收付金額,幣別
交易類別只處理 現股買進／定期定額（視為買進）與 現股賣出（視為賣出）。

成本採「移動平均法」：每次買進把 (成交股數*成交單價 + 手續費) 併入該股票的成本池，
賣出時依目前平均成本比例扣減成本池與股數，剩餘股數的平均成本 = 剩餘成本池 / 剩餘股數。

--min-pct 依「淨部位成本佔全部持股成本池的百分比」篩選，只保留較大部位
（預設 1.0，即只保留佔比 >= 1% 的持股），避免把幾百檔 1 股的零股全部塞進報告。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

STOCK_ID_PATTERN = re.compile(r"\(([0-9A-Za-z]+)\)\s*$")


def parse_transactions(path: Path) -> list[dict]:
    with open(path, "rb") as fh:
        raw = fh.read()
    text = raw.decode("big5")
    lines = [line for line in text.splitlines() if line.strip()]

    rows = []
    for line in lines[1:]:  # 跳過表頭
        cols = [c.strip() for c in line.split(",")]
        if len(cols) < 6:
            continue
        date, tx_type, name_field, qty, price, _amount = cols[:6]
        fee = float(cols[6]) if len(cols) > 6 and cols[6] else 0.0

        match = STOCK_ID_PATTERN.search(name_field)
        if not match:
            print(f"[warn] 無法從「{name_field}」解析股票代號，略過此列", file=sys.stderr)
            continue
        stock_id = match.group(1)
        name = name_field[: match.start()].strip() or stock_id

        rows.append(
            {
                "date": date,
                "type": tx_type,
                "stock_id": stock_id,
                "name": name,
                "qty": float(qty),
                "price": float(price),
                "fee": fee,
            }
        )
    return rows


def compute_moving_average_cost(rows: list[dict]) -> dict[str, dict]:
    """回傳 {stock_id: {"name","shares","cost_basis"}}，只含賣完前剩餘股數 > 0 的股票。"""
    positions: dict[str, dict] = {}

    for row in sorted(rows, key=lambda r: r["date"]):
        stock_id = row["stock_id"]
        pos = positions.setdefault(stock_id, {"name": row["name"], "shares": 0.0, "cost_pool": 0.0})

        if row["type"] in ("現股買進", "定期定額"):
            pos["shares"] += row["qty"]
            pos["cost_pool"] += row["qty"] * row["price"] + row["fee"]
        elif row["type"] == "現股賣出":
            if pos["shares"] > 0:
                avg_cost = pos["cost_pool"] / pos["shares"]
                sell_qty = min(row["qty"], pos["shares"])
                pos["cost_pool"] -= avg_cost * sell_qty
                pos["shares"] -= sell_qty
        else:
            print(f"[warn] 未知交易類別「{row['type']}」，略過", file=sys.stderr)

    result = {}
    for stock_id, pos in positions.items():
        if pos["shares"] <= 0:
            continue
        result[stock_id] = {
            "name": pos["name"],
            "shares": pos["shares"],
            "cost_basis": round(pos["cost_pool"] / pos["shares"], 4),
        }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("transactions_csv", type=Path, help="富邦成交紀錄 CSV 路徑")
    parser.add_argument("--min-pct", type=float, default=1.0, help="只保留成本佔比 >= 此百分比的持股（預設 1.0）")
    parser.add_argument("--out", type=Path, default=Path("config/holdings.json"))
    parser.add_argument("--cash", type=float, default=0.0, help="目前現金餘額（本工具無法從交易紀錄推得，需手動指定）")
    args = parser.parse_args()

    rows = parse_transactions(args.transactions_csv)
    positions = compute_moving_average_cost(rows)

    total_cost = sum(p["shares"] * p["cost_basis"] for p in positions.values())
    kept = []
    dropped = []
    for stock_id, pos in sorted(positions.items()):
        market_cost = pos["shares"] * pos["cost_basis"]
        pct = (market_cost / total_cost * 100) if total_cost else 0.0
        entry = {
            "stock_id": stock_id,
            "name": pos["name"],
            "shares": pos["shares"],
            "cost_basis": pos["cost_basis"],
        }
        if pct >= args.min_pct:
            kept.append(entry)
        else:
            dropped.append((stock_id, pos["name"], pct))

    holdings_json = {
        "cash": args.cash,
        "holdings": kept,
        "new_cash_inflow_today": False,
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(holdings_json, fh, ensure_ascii=False, indent=2)

    print(f"保留 {len(kept)} 檔（佔比 >= {args.min_pct}%），已寫入 {args.out}")
    print(f"篩掉 {len(dropped)} 檔零散部位（佔比 < {args.min_pct}%）：")
    for stock_id, name, pct in dropped:
        print(f"  {stock_id} {name}: {pct:.2f}%")
    print(f"\n⚠️  cash 目前是 {args.cash}（預設 0），需要你自己確認交割戶餘額後手動修改 {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
