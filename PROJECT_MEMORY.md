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
- **資料源**：[FinMind API](https://finmindtrade.com/)（v4，`https://api.finmindtrade.com/api/v4/data`）。原計劃書列出 TWSE/TPEx OpenAPI 為候選，但兩者格式不同、財報需分別串接；FinMind 用同一套介面涵蓋 TWSE＋TPEx 的股價、財報、PER/PBR/殖利率，故 Phase 0 決定採用（見第 6 節）
- **策略引擎**：純 Python 通用引擎，讀取 `strategy_*.json` 執行篩選／排名／進出場訊號判斷；新增策略只需新增一份 JSON，不需改 Python 程式碼
- **報告資料**：每日產出 `reports/YYYY-MM-DD/report.json`（Model），永久保存於 repo
- **Dashboard**：純靜態網站，GitHub Pages 直接讀取報告 JSON 渲染（HTML + JS 圖表庫，如 Chart.js），不依賴後端伺服器
- **Email 通知**：GitHub Actions 內用 Python 寄信，內容為 View（由同一份報告 JSON 渲染成 HTML Email）
- **儲存**：全部檔案存在 GitHub repo，不需另建資料庫

### 檔案／資料夾用途

| 路徑 | 用途 | 狀態 |
|---|---|---|
| `src/data_sources/finmind.py` | FinMind API 客戶端（股價/財報/PER），失敗回傳 `FetchResult(ok=False, ...)` 不拋例外 | 已建立（Phase 0） |
| `scripts/verify_phase0.py` | Phase 0 驗證腳本，對應 T0-1～T0-4 | 已建立（Phase 0） |
| `.github/workflows/phase0-verify.yml` | 手動觸發（workflow_dispatch）執行驗證，上傳 `phase0_snapshot.json` 快照 | 已建立（Phase 0） |
| `requirements.txt` | 雲端（GitHub Actions）用相依套件：`requests`、`python-dotenv` | 已建立 |
| `requirements-broker.txt` | 富邦 API 本機專用相依套件說明（不含 fubon_neo，需另外用官方 wheel 安裝） | 已建立 |
| `strategy_*.json` | 選股策略定義，JSON Schema 驅動 | 規劃中，Phase 1 建立 |
| `reports/YYYY-MM-DD/report.json` | 每日報告 Model，歷史保留 | 規劃中，Phase 3 建立 |
| `dashboard/` | GitHub Pages 靜態 Dashboard（View） | 規劃中，Phase 4 建立 |
| `fubon_client.py` | 富邦證券 API 連線與持股查詢（既有，與本專案獨立，僅本機執行） | 已建立（本專案之前） |

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

- **已完成**：Phase 0　資料源驗證 — **Gate 已通過**（使用者於本機 Windows + Python 3.12 執行 `scripts/verify_phase0.py` 驗證，2026-08-03）
  - T0-1（近一年日 K 線完整度）：2330／2317／0050 各 266 筆，日期連續無缺漏 — PASS
  - T0-2（財報欄位可用性）：2330／2317 的 EPS、Revenue、IncomeAfterTaxes、EquityAttributableToOwnersOfParent、PER 均可正確取得數值；0050 為 ETF，無公司財報／PER，驗證腳本已改為對 ETF 自動略過此項而非判定失敗 — PASS
  - T0-3（執行時間 < 5 分鐘）：實測 1.7 秒 — PASS
  - T0-4（資料源異常處理）：不存在的股票代號、連線失敗兩種情境皆正確回傳 `FetchResult(ok=False)`，未拋例外中斷流程 — PASS
  - 尚待人工確認：T0-2「財報數字與公開資訊誤差 < 1%」需對照公開來源核對 `phase0_snapshot.json` 數值（非阻斷性，非自動化項目）
- **進行中**：Phase 1　指標計算與策略引擎（JSON 驅動）
- **已知限制**：
  - 開發用雲端 sandbox 連不到 `api.finmindtrade.com`，此限制會持續影響後續所有 Phase 的資料驗證，皆須在 GitHub Actions 或使用者本機執行後回報結果
  - `requirements.txt` / `requirements-broker.txt` 曾因檔案內中文註解，在 Windows 繁體中文語系（cp950）下被 `pip install -r` 讀取時噴 `UnicodeDecodeError`，已改為純英文註解修正；日後新增 requirements 檔案應避免非 ASCII 字元

## 6. 資料源清單與已知限制/風險

| 候選資料源 | 狀態 | 備註 |
|---|---|---|
| **FinMind API** | **已選定，Phase 0 驗證通過** | 見 `src/data_sources/finmind.py`。免登入可用但請求額度低，建議設定 `FINMIND_TOKEN` |
| 台灣證交所 OpenAPI (TWSE OpenData) | 已否決 | 與 TPEx 格式不同，財報需另外串接，改用 FinMind 統一介面 |
| 櫃買中心 OpenAPI (TPEx) | 已否決 | 同上 |
| 富邦 API（`fubon_neo`/`fugle-marketdata`） | 不採用於本專案 | 需要憑證+帳密才能取得行情，不適合放進 GitHub Actions 自動排程；富邦 API 僅用於 `fubon_client.py` 本機查詢實際持股，與本專案分工 |

風險：
- 資料源逾時/空值需能被程式正確記錄且不中斷整體流程 — 已在 `finmind.py`／`verify_phase0.py` 的 T0-4 驗證通過
- FinMind 未登入時有請求頻率限制（HTTP 402），需視 Phase 6（多組合）用量評估是否需要付費 token
- 目前開發所在的雲端 sandbox 連不到 `api.finmindtrade.com`（proxy 白名單限制），所有 Phase 0 之後的資料驗證都必須在 GitHub Actions 或使用者本機執行，這是持續到專案結束的限制，非一次性問題

## 7. 變更紀錄（Changelog）

- 2026-08-03：建立 PROJECT_MEMORY.md，記錄專案計劃書內容，尚未開始任何 Phase 實作。
- 2026-08-03：完成 Phase 0 程式（FinMind 客戶端、驗證腳本、GitHub Actions workflow）。選定 FinMind 為資料源。T0-4 本機驗證通過；T0-1/T0-2/T0-3 因開發環境網路限制無法在此驗證，待使用者於 GitHub Actions 或本機執行後回報結果，才能判定 Phase 0 Gate 是否通過、可否進入 Phase 1。
- 2026-08-03：使用者於本機執行 `scripts/verify_phase0.py`，T0-1/T0-3/T0-4 全數通過；T0-2 對 0050（ETF）回報缺少財報/PER 欄位。確認為預期行為（ETF 無公司財報），調整驗證腳本對 ETF 自動略過該項檢查而非判定失敗。同時修正 `requirements.txt`／`requirements-broker.txt` 因中文註解在 Windows cp950 語系下造成 `pip install` 的 `UnicodeDecodeError`。**Phase 0 Gate 全數通過，進入 Phase 1**。
