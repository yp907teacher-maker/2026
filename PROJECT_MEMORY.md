# PROJECT_MEMORY.md

專案記憶文件，供下次開發或其他協作者快速上手。每完成一個 Phase 請更新此文件，作為交接與延續開發的單一事實來源。

## 1. 專案目的與範圍邊界

**台股每日分析與通知系統**：純資訊整理、排名計算與視覺化，**不構成投資建議、不自動下單交易**。

- 市場：台灣證券交易所（TWSE）＋ 櫃買中心（TPEx）
- 幣別：TWD
- 交易：系統只產出「建議名單」與提醒，實際下單由使用者自行在券商 App 操作
- 持倉/現金：手動輸入或匯入券商對帳單 CSV，系統負責計算與視覺化，非真實下單帳戶

與本 repo 既有的 `fubon_client.py`（富邦證券 API 連線/查詢框架）是**兩個獨立用途**：
`fubon_client.py` 負責券商端登入與查詢（目前下單功能停用），本專案負責公開行情資料的抓取、選股排名、報告產出與通知，兩者不互相依賴。

## 2. 系統架構

```
GitHub Actions（排程）
  → 抓取台股行情/財報
  → 技術指標計算
  → 依策略 JSON 排名選股
  → 產生報告 JSON
  → 寫入 GitHub Pages Dashboard
  → 寄送 Email
```

- **資料抓取／運算**：Python，跑在 GitHub Actions（cron，台灣時間每日 06:00 前完成）
- **資料源**：台灣證交所 OpenAPI、櫃買中心 OpenAPI，或第三方台股歷史行情/財報 API（尚待 Phase 0 評估確定，見第 6 節）
- **策略引擎**：純 Python 通用引擎，讀取 `strategy_*.json` 執行篩選／排名／進出場訊號判斷；新增策略只需新增一份 JSON，不需改 Python 程式碼
- **報告資料**：每日產出 `reports/YYYY-MM-DD/report.json`（Model），永久保存於 repo
- **Dashboard**：純靜態網站，GitHub Pages 直接讀取報告 JSON 渲染（HTML + JS 圖表庫，如 Chart.js），不依賴後端伺服器
- **Email 通知**：GitHub Actions 內用 Python 寄信，內容為 View（由同一份報告 JSON 渲染成 HTML Email）
- **儲存**：全部檔案存在 GitHub repo，不需另建資料庫

### 檔案／資料夾用途（規劃中，尚未建立）

| 路徑 | 用途 |
|---|---|
| `strategy_*.json` | 選股策略定義，JSON Schema 驅動 |
| `reports/YYYY-MM-DD/report.json` | 每日報告 Model，歷史保留 |
| `dashboard/` | GitHub Pages 靜態 Dashboard（View） |
| `.github/workflows/` | GitHub Actions 排程（抓資料/選股/報告/Email） |
| `fubon_client.py` | 富邦證券 API 連線與查詢（既有，與本專案獨立） |

## 3. 策略 JSON Schema 說明

沿用 `trading_strategy_schema_v2_complete.json` 架構，調整重點：

- `strategy.market`: `"TW_STOCK"`，`base_currency`: `"TWD"`
- `universe.exchanges`: `["TWSE", "TPEx"]`
- **移除** `execution` 區塊（不自動下單），改為 `output` 區塊描述建議名單呈現方式
- 保留 `filters`、`indicators`、`derived_factors`、`ranking`、`entry_signals`、`exit_signals`（entry/exit 訊號僅作提醒條件，不觸發下單）
- `portfolio.target_position_pct` 固定 `0.10`，`allow_fractional_shares: false`，`lot_size: 1`
- `rebalance.trigger`: `["new_cash_inflow", "monthly_first_trading_day"]`，移除固定週頻率
- `backtest.benchmark`: `"0050"` 或 `"TAIEX"`

範例骨架：

```json
{
  "strategy": { "market": "TW_STOCK", "base_currency": "TWD" },
  "universe": { "exchanges": ["TWSE", "TPEx"] },
  "portfolio": {
    "target_position_pct": 0.10,
    "max_positions": 10,
    "allow_fractional_shares": false,
    "lot_size": 1,
    "min_order_value": 1000
  },
  "rebalance": {
    "trigger": ["new_cash_inflow", "monthly_first_trading_day"],
    "frequency": "event_driven"
  }
}
```

同一追蹤組合同時只能套用一個策略，但可隨時更換。

## 4. report.json 欄位定義（Model 規格）

尚未實作，Phase 3 完成後於此補上完整欄位定義。預期至少包含：現金、持倉（代號/股數/成本/現價/市值/佔比/損益%）、個股績效（1日/1週/1月%）、PE、每日前十強、次日預測名單（含信心度）、關注類股表現、NAV/回撤序列。

## 5. 目前進度

- **已完成**：無（規劃階段）
- **進行中**：無，等待開始 Phase 0
- **已知限制**：資料源尚未選定與驗證（見第 6 節）

## 6. 資料源清單與已知限制/風險

| 候選資料源 | 狀態 | 備註 |
|---|---|---|
| 台灣證交所 OpenAPI (TWSE OpenData) | 待評估 | 需確認欄位涵蓋率與更新頻率 |
| 櫃買中心 OpenAPI (TPEx) | 待評估 | 同上 |
| 第三方台股行情/財報 API | 待評估 | 需評估請求限制與延遲，作為 Phase 0 任務 |

風險：資料源逾時/空值需能被程式正確記錄且不中斷整體流程（見 Phase 0 測試案例 T0-4）。

## 7. 變更紀錄（Changelog）

- 2026-08-03：建立 PROJECT_MEMORY.md，記錄專案計劃書內容，尚未開始任何 Phase 實作。
