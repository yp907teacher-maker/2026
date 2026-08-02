"""FinMind 台股資料源客戶端。

資料源：https://finmindtrade.com/ FinMind API v4
提供股價日 K、財報、PER/PBR/殖利率等台股資料，TWSE 與 TPEx 共用同一介面。

設計原則（對應 Phase 0 測試案例 T0-4）：
所有對外請求失敗時回傳 FetchResult(ok=False, error=...)，不拋出例外，
讓呼叫端可以記錄錯誤並繼續處理其他股票，不中斷整體流程。
"""

import os
import time
from dataclasses import dataclass, field
from typing import Any

import requests

API_URL = "https://api.finmindtrade.com/api/v4/data"

DATASET_PRICE = "TaiwanStockPrice"
DATASET_FINANCIAL = "TaiwanStockFinancialStatements"
DATASET_PER = "TaiwanStockPER"
DATASET_INFO = "TaiwanStockInfo"


@dataclass
class FetchResult:
    """統一的抓取結果，成功與失敗都用同一個型別表達。"""

    ok: bool
    data: list[dict[str, Any]] = field(default_factory=list)
    error: str = ""
    dataset: str = ""
    data_id: str = ""

    def __len__(self) -> int:
        return len(self.data)


class FinMindClient:
    def __init__(self, token: str | None = None, timeout: int = 30, max_retries: int = 3):
        self.token = token if token is not None else os.environ.get("FINMIND_TOKEN", "")
        self.timeout = timeout
        self.max_retries = max_retries
        self.session = requests.Session()

    def _request(self, params: dict[str, Any]) -> FetchResult:
        dataset = params.get("dataset", "")
        data_id = params.get("data_id", "")

        if self.token:
            params = {**params, "token": self.token}

        last_error = ""
        for attempt in range(self.max_retries):
            try:
                resp = self.session.get(API_URL, params=params, timeout=self.timeout)
            except requests.RequestException as exc:
                last_error = f"連線失敗: {exc}"
            else:
                if resp.status_code == 402:
                    return FetchResult(
                        ok=False,
                        error="超過 API 請求額度上限（FinMind 未登入每小時限制較低，建議設定 FINMIND_TOKEN）",
                        dataset=dataset,
                        data_id=data_id,
                    )
                if resp.status_code != 200:
                    last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
                else:
                    try:
                        payload = resp.json()
                    except ValueError as exc:
                        last_error = f"回應非合法 JSON: {exc}"
                    else:
                        data = payload.get("data")
                        if data is None:
                            last_error = f"回應缺少 data 欄位: {str(payload)[:200]}"
                        else:
                            return FetchResult(
                                ok=True, data=data, dataset=dataset, data_id=data_id
                            )

            if attempt < self.max_retries - 1:
                time.sleep(2**attempt)

        return FetchResult(ok=False, error=last_error, dataset=dataset, data_id=data_id)

    def get_stock_list(self) -> FetchResult:
        """取得台股上市櫃股票清單（含代號、名稱、產業別、交易所）。"""
        return self._request({"dataset": DATASET_INFO})

    def get_daily_price(self, stock_id: str, start_date: str, end_date: str) -> FetchResult:
        """取得日 K 線。欄位：date, open, max, min, close, Trading_Volume 等。"""
        return self._request(
            {
                "dataset": DATASET_PRICE,
                "data_id": stock_id,
                "start_date": start_date,
                "end_date": end_date,
            }
        )

    def get_financial_statements(
        self, stock_id: str, start_date: str, end_date: str
    ) -> FetchResult:
        """取得財報。長格式：每列一個 type（如 EPS、Revenue），欄位 date/type/value。"""
        return self._request(
            {
                "dataset": DATASET_FINANCIAL,
                "data_id": stock_id,
                "start_date": start_date,
                "end_date": end_date,
            }
        )

    def get_per_pbr(self, stock_id: str, start_date: str, end_date: str) -> FetchResult:
        """取得每日本益比、股價淨值比、殖利率。欄位：date, PER, PBR, dividend_yield。"""
        return self._request(
            {
                "dataset": DATASET_PER,
                "data_id": stock_id,
                "start_date": start_date,
                "end_date": end_date,
            }
        )
