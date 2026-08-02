"""Phase 0 資料源驗證腳本。

執行方式：
    python scripts/verify_phase0.py

對應計劃書 Phase 0 的四項測試案例：
    T0-1  對 2330 / 2317 / 0050 抓取近 1 年日 K 線，資料無缺漏
    T0-2  抓取財報欄位（EPS、營收、ROE 相關）並輸出供人工比對
    T0-3  可在 GitHub Actions 手動觸發成功執行並產生 log，執行時間 < 5 分鐘
    T0-4  資料源異常時能記錄錯誤且不中斷整體流程

離開碼 0 表示自動可判定的項目全數通過，1 表示有項目失敗。
"""

import json
import os
import sys
import time
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import src.data_sources.finmind as finmind_module  # noqa: E402
from src.data_sources.finmind import FinMindClient  # noqa: E402

TEST_STOCKS = ["2330", "2317", "0050"]

# 台股一年約 240～250 個交易日，扣除長假與個股停牌，低於此門檻視為資料缺漏。
MIN_TRADING_DAYS = 220

PRICE_FIELDS = ["date", "open", "max", "min", "close", "Trading_Volume"]

# T0-2 需要人工比對的財報項目（FinMind 財報為長格式，type 欄位值）
FINANCIAL_TYPES = ["EPS", "Revenue", "IncomeAfterTaxes", "EquityAttributableToOwnersOfParent"]


class Checks:
    def __init__(self) -> None:
        self.results: list[tuple[str, bool, str]] = []

    def record(self, name: str, passed: bool, detail: str = "") -> None:
        self.results.append((name, passed, detail))
        mark = "PASS" if passed else "FAIL"
        print(f"  [{mark}] {name}" + (f" — {detail}" if detail else ""))

    @property
    def all_passed(self) -> bool:
        return all(passed for _, passed, _ in self.results)


def check_price_continuity(rows: list[dict]) -> tuple[bool, str]:
    """檢查日 K 資料筆數、欄位完整性、日期是否重複或亂序。"""
    if len(rows) < MIN_TRADING_DAYS:
        return False, f"僅 {len(rows)} 筆，低於門檻 {MIN_TRADING_DAYS}"

    dates = [r.get("date") for r in rows]
    if len(set(dates)) != len(dates):
        return False, "日期有重複"
    if dates != sorted(dates):
        return False, "日期未依序排列"

    for row in rows:
        for f in PRICE_FIELDS:
            if row.get(f) is None:
                return False, f"{row.get('date')} 的 {f} 為空值"

    return True, f"{len(rows)} 筆，{dates[0]} ~ {dates[-1]}"


def run_t0_1(client: FinMindClient, checks: Checks, start: str, end: str) -> dict:
    print("\nT0-1　近一年日 K 線完整度")
    snapshot = {}
    for stock_id in TEST_STOCKS:
        result = client.get_daily_price(stock_id, start, end)
        if not result.ok:
            checks.record(f"T0-1 {stock_id}", False, f"抓取失敗: {result.error}")
            continue
        passed, detail = check_price_continuity(result.data)
        checks.record(f"T0-1 {stock_id}", passed, detail)
        if result.data:
            snapshot[stock_id] = result.data[-1]
    return snapshot


def run_t0_2(client: FinMindClient, checks: Checks, start: str, end: str) -> dict:
    """抓取財報與 PER。

    誤差 < 1% 的比對需要外部公開數字作為基準，無法由程式自行判定，
    因此此處驗證「欄位存在且可解析為數值」，並輸出最新一期數字供人工比對。
    """
    print("\nT0-2　財報欄位可用性（數值另存 phase0_financial_snapshot.json 供人工比對）")
    snapshot: dict = {}

    for stock_id in TEST_STOCKS:
        result = client.get_financial_statements(stock_id, start, end)
        if not result.ok:
            checks.record(f"T0-2 {stock_id} 財報", False, f"抓取失敗: {result.error}")
            continue

        found: dict[str, dict] = {}
        for row in result.data:
            row_type = row.get("type")
            if row_type in FINANCIAL_TYPES:
                value = row.get("value")
                if isinstance(value, (int, float)):
                    prev = found.get(row_type)
                    if prev is None or row.get("date", "") >= prev["date"]:
                        found[row_type] = {"date": row.get("date"), "value": value}

        missing = [t for t in FINANCIAL_TYPES if t not in found]
        checks.record(
            f"T0-2 {stock_id} 財報",
            not missing,
            f"取得 {list(found)}" if not missing else f"缺少欄位 {missing}",
        )

        per_result = client.get_per_pbr(stock_id, start, end)
        if not per_result.ok:
            checks.record(f"T0-2 {stock_id} PER", False, f"抓取失敗: {per_result.error}")
        else:
            latest = per_result.data[-1] if per_result.data else {}
            has_per = isinstance(latest.get("PER"), (int, float))
            checks.record(
                f"T0-2 {stock_id} PER",
                has_per,
                f"{latest.get('date')} PER={latest.get('PER')}" if has_per else "PER 無數值",
            )
            found["PER"] = latest

        snapshot[stock_id] = found

    return snapshot


def run_t0_4(checks: Checks) -> None:
    """故意觸發異常，確認程式回傳錯誤而非拋例外中斷。"""
    print("\nT0-4　資料源異常處理")

    bad_client = FinMindClient(timeout=1, max_retries=1)
    try:
        result = bad_client.get_daily_price("NOT_A_REAL_STOCK_ID", "2020-01-01", "2020-01-05")
    except Exception as exc:  # noqa: BLE001 - 這裡就是要確認不會有例外逸出
        checks.record("T0-4 不存在的股票代號", False, f"拋出例外中斷流程: {exc!r}")
    else:
        checks.record(
            "T0-4 不存在的股票代號",
            True,
            "回傳空資料" if result.ok else f"回傳錯誤字串: {result.error[:60]}",
        )

    offline = FinMindClient(timeout=2, max_retries=1)
    original_url = finmind_module.API_URL
    try:
        finmind_module.API_URL = "https://finmind-does-not-exist.invalid/api/v4/data"
        result = offline.get_daily_price("2330", "2024-01-01", "2024-01-05")
    except Exception as exc:  # noqa: BLE001
        checks.record("T0-4 連線失敗", False, f"拋出例外中斷流程: {exc!r}")
    else:
        checks.record(
            "T0-4 連線失敗",
            not result.ok and bool(result.error),
            f"已記錄錯誤: {result.error[:60]}",
        )
    finally:
        finmind_module.API_URL = original_url


def main() -> int:
    started = time.time()
    end = date.today()
    start = end - timedelta(days=400)
    start_str, end_str = start.isoformat(), end.isoformat()

    token = os.environ.get("FINMIND_TOKEN", "")
    print(f"Phase 0 資料源驗證　資料區間 {start_str} ~ {end_str}")
    print(f"FINMIND_TOKEN：{'已設定' if token else '未設定（請求額度較低，可能觸發限制）'}")

    client = FinMindClient()
    checks = Checks()

    price_snapshot = run_t0_1(client, checks, start_str, end_str)
    financial_snapshot = run_t0_2(client, checks, start_str, end_str)
    run_t0_4(checks)

    elapsed = time.time() - started
    print("\nT0-3　執行時間")
    checks.record("T0-3 執行時間 < 5 分鐘", elapsed < 300, f"實際 {elapsed:.1f} 秒")

    out_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "phase0_snapshot.json")
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(
            {"generated_at": end_str, "latest_price": price_snapshot, "financial": financial_snapshot},
            fh,
            ensure_ascii=False,
            indent=2,
        )
    print(f"\n數值快照已寫入 {out_path}（供 T0-2 人工比對公開數字）")

    failed = [name for name, passed, _ in checks.results if not passed]
    print("\n" + "=" * 60)
    if checks.all_passed:
        print(f"Phase 0 自動檢查全數通過（{len(checks.results)} 項）")
        print("尚需人工確認：T0-2 財報數字與公開資訊誤差 < 1%、T0-3 於 GitHub Actions 手動觸發成功")
        return 0

    print(f"未通過項目（{len(failed)} 項）：")
    for name in failed:
        print(f"  - {name}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
