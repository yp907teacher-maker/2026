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

### 1.1 隱私與公開架構（重要，2026-08-03 確定）

使用者計畫日後把這個 repo 改成**公開**（因為 GitHub Pages 在免費方案下只能用公開 repo 架設 Dashboard）。但真實持股資料（現金金額、股數、成本、市值）**絕對不能**進公開 repo。因此系統分成「完整版」與「公開版」兩份平行資料：

| | 完整版 | 公開版 |
|---|---|---|
| 內容 | 現金金額、每檔股數/成本/市值/現價、總資產 + 全部非敏感欄位 | 只有現金**佔比%**、持股**佔比%**/損益%/績效%/PE，**沒有**股數、成本、市值、現價、總資產 |
| 存放路徑 | `reports/YYYY-MM-DD/report.json` | `reports_public/YYYY-MM-DD/report.json` |
| 是否進 git | **否**，`.gitignore` 排除，只存在本機/私人環境 | **是**，會 commit，供公開 repo／GitHub Pages Dashboard 讀取 |
| 產生方式 | `report_builder.build_report()` / `save_report()` | `report_schema.build_public_report()` 從完整版拿掉敏感欄位，`report_builder.save_public_report()` 寫檔 |
| Schema | `report_schema.REPORT_SCHEMA` | `report_schema.PUBLIC_REPORT_SCHEMA` |

`config/holdings.json`（使用者真實持股設定檔）同樣被 `.gitignore` 排除，只保留 `config/holdings.example.json` 作為公開的格式範例。

NAV 曲線（`nav_history`）本身是相對值（以某天為 1.0 基準的比值），**兩個版本都保留**，不算洩漏——但用來算 NAV 的基準值 `baseline_total_value`（絕對金額）只存在完整版旁邊的 `reports/nav_state.json`，該檔案也被 `.gitignore` 排除。

**尚未解決的限制**：GitHub Actions 每次執行都是全新環境，沒有本機硬碟持久化。`config/holdings.json` 不進 git，代表 Actions 上執行時抓不到真實持股，除非透過 GitHub Secret（`HOLDINGS_JSON`）在執行當下寫入（見 `.github/workflows/daily-pipeline.yml`，執行完不會被 commit）。但 `reports/nav_state.json`、`reports/rebalance_state.json` 這兩個「跨日狀態檔」目前完全沒有機制在 GitHub Actions 執行之間保留——每次 Actions 執行都會是「全新的第一天」（NAV 重新從 1.0 開始、再平衡狀態重置）。這代表：**目前只有在同一台機器上連續本機執行，NAV 曲線與再平衡邏輯才能正確累積跨日狀態；純靠 GitHub Actions 自動排程還無法正確累積這兩項。** 之後要嘛（a）固定在本機執行、Actions 只是輔助，要嘛（b）之後研究把這兩個狀態檔也透過 GitHub Secret 或其他私人儲存機制跨執行持久化，目前尚未實作，先誠實記錄這個缺口。

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
| `requirements.txt` | 雲端（GitHub Actions）用相依套件：`requests`、`python-dotenv`、`jsonschema` | 已建立 |
| `requirements-broker.txt` | 富邦 API 本機專用相依套件說明（不含 fubon_neo，需另外用官方 wheel 安裝） | 已建立 |
| `requirements-dev.txt` | 測試用相依套件（`pytest`），與雲端排程用的 `requirements.txt` 分開 | 已建立（Phase 1） |
| `src/indicators.py` | SMA/EMA/RSI/MACD/ATR/布林通道/ADX 指標計算，回傳與輸入等長的 list，資料不足處為 `None` | 已建立（Phase 1） |
| `src/expr.py` | 安全運算式求值器（基於 `ast`），供策略 JSON 的 filters/derived_factors/entry_signals/exit_signals 使用，不執行任意程式碼 | 已建立（Phase 1） |
| `src/strategy_engine.py` | 讀取策略 dict，計算指標→衍生因子→篩選→排名→進出場訊號，`rank_stocks()` 為主要進入點 | 已建立（Phase 1） |
| `strategies/strategy_momentum.json` | 範例策略：動能（20日動能排名，SMA20>SMA60 濾網） | 已建立（Phase 1） |
| `strategies/strategy_meanreversion.json` | 範例策略：均值回歸（RSI 超賣＋布林下軌） | 已建立（Phase 1） |
| `tests/test_indicators.py` | 指標正確性測試，對應 T1-1 | 已建立（Phase 1） |
| `tests/test_strategy_engine.py` | 策略引擎測試，對應 T1-2／T1-3／T1-4 | 已建立（Phase 1） |
| `src/predictor.py` | 次日預測模組：以排名分數線性趨勢外插預測次日分數，`predict_next_day()` 單次預測、`walk_forward_backtest()` 逐日滾動回測記錄重疊率 | 已建立（Phase 2） |
| `tests/test_predictor.py` | 預測模組測試，對應 T2-1／T2-2／T2-3 | 已建立（Phase 2） |
| `.github/workflows/unit-tests.yml`（原 `phase1-test.yml`） | push 到 `src/`／`strategies/`／`tests/` 或手動觸發時跑 `pytest tests/`（涵蓋 Phase 1＋2＋3 所有測試） | 已建立（Phase 1，Phase 2／3 沿用同一個 workflow） |
| `src/portfolio.py` | 現金＋持股快照：`compute_performance_pct()` 算 1日/1週/1月報酬率、`build_holding()`／`build_portfolio_snapshot()` 算市值與佔比 | 已建立（Phase 3） |
| `src/rebalance.py` | 再平衡觸發規則：`run_rebalance_calendar()` 依「新資金匯入」／「當月第一個交易日」觸發，逐月配額不重複觸發 | 已建立（Phase 3） |
| `src/report_schema.py` | 完整版 `REPORT_SCHEMA` ＋ 公開版 `PUBLIC_REPORT_SCHEMA`、`validate_report()`／`validate_public_report()`、`build_public_report()`（去敏感化） | 已建立（Phase 3），公開版於 2026-08-03 新增 |
| `src/report_builder.py` | `build_report()`／`save_report()`／`load_report()`（完整版，不進 git）＋ `save_public_report()`／`load_public_report()`（公開版，進 git） | 已建立（Phase 3），公開版於 2026-08-03 新增 |
| `tests/test_public_report.py` | 驗證公開版確實拿掉所有絕對金額欄位、保留相對值欄位、通過自己的 Schema，並用字串比對確認檔案內容找不到金額數字 | 已建立（2026-08-03） |
| `scripts/convert_holdings_csv.py` | 把富邦「成交紀錄」CSV（Big5）轉成 `config/holdings.json`：以移動平均法算各檔剩餘股數與成本，並依成本佔比門檻篩掉零散部位 | 已建立（2026-08-03） |
| `tests/test_portfolio.py` | 對應 T3-1（績效%計算） | 已建立（Phase 3） |
| `tests/test_report_builder.py` | 對應 T3-2（連續多日報告互不覆蓋）、T3-3（JSON Schema 驗證） | 已建立（Phase 3） |
| `tests/test_rebalance.py` | 對應 T3-4（再平衡觸發規則、僅觸發一次） | 已建立（Phase 3） |
| `src/nav.py` | `compute_nav_entry()` 算當日 NAV／回撤（狀態跨日持久化）、`append_nav_history()` 累積歷史不重複 | 已建立（Phase 3 收尾） |
| `src/score_history.py` | 排名分數的多日滾動快照儲存，`to_predictor_input()` 轉成 predictor 需要的格式 | 已建立（Phase 3 收尾） |
| `src/sectors.py` | `build_watched_sectors()`：依設定檔的代表股清單算各關注類股當日平均漲跌幅 | 已建立（Phase 3 收尾） |
| `tests/test_nav.py`／`test_score_history.py`／`test_sectors.py` | 分別對應上面三個模組的正確性測試 | 已建立（Phase 3 收尾） |
| `config/universe.json` | 策略引擎每日評分的候選股清單（精選 30 檔，非全市場，避免 FinMind 免費額度打爆） | 已建立（Phase 3 收尾） |
| `config/holdings.json` | 使用者手動維護的現金＋實際持股，含 `new_cash_inflow_today` 手動旗標（供再平衡判斷用，不自動推斷）。**已於 2026-08-03 從 git 移除並加入 `.gitignore`**，只存在本機；GitHub Actions 執行時改由 `HOLDINGS_JSON` Secret 在執行當下寫入 | 不進 git，待使用者於本機填入真實持股 |
| `config/holdings.example.json` | `holdings.json` 的格式範例（公開，只有假資料） | 已建立（Phase 3 收尾） |
| `config/watched_sectors.json` | 三大關注類股設定：半導體（2330/2454/3711）、AI（3231/2382/6669）、金融（2882/2881/2891） | 已建立（Phase 3 收尾），已依使用者指示設定完成 |
| `scripts/daily_pipeline.py` | **每日整合腳本**：`run_pipeline()` 是不碰網路/檔案的純函式（串接 rank_stocks→score_history→predictor→portfolio→sectors→nav→rebalance→report_builder），`main()` 負責讀設定檔、呼叫 FinMind、寫入 `reports/` 與各狀態檔 | 已建立，`run_pipeline()` 邏輯以合成資料測試通過；`main()` 串接真實 FinMind 需連網環境執行 |
| `tests/test_daily_pipeline.py` | 用合成資料跑 `run_pipeline()` 驗證單次執行、連續 5 天不互相污染、資金匯入觸發再平衡、缺資料股票不中斷流程 | 已建立 |
| `.github/workflows/daily-pipeline.yml` | 手動觸發執行 `daily_pipeline.py` 並把 `reports/` 的變更 commit 回 repo；等 Phase 5 做完 Email 才會改成台灣時間 06:00 的排程 | 已建立 |
| `reports/YYYY-MM-DD/report.json` | 每日報告 Model **完整版**（含真實金額），`.gitignore` 排除，只存在本機 | **已有第一筆真實資料**：2026-07-31，使用者本機執行 `daily_pipeline.py` 產生，22 檔持股、市值、損益% 皆已人工核對正確 |
| `reports_public/YYYY-MM-DD/report.json` | 每日報告 Model **公開版**（去敏感化），會 commit，供公開 repo／Dashboard 讀取 | 2026-07-31 這筆已 commit 進 `claude/github-login-o83wwg` 分支（commit `b6588dc`），內容不含金額，已用 `PUBLIC_REPORT_SCHEMA` 驗證通過 |
| `reports/score_history.json` | 排名分數多日快照（只有分數，無金額）**會 commit**，讓 GitHub Actions 之間能累積預測所需的歷史 | 已有第一筆真實資料並 commit（2026-07-31 這天的排名分數） |
| `reports/nav_state.json`／`reports/rebalance_state.json` | NAV 基準值與再平衡跨日狀態，含絕對金額，**不進 git**；因此 GitHub Actions 之間無法累積（見 1.1 節末段的未解限制） | 本機已產生（`config/holdings.json` 目前 `cash` 仍是 0，待使用者填入真實交割戶餘額後 NAV／總資產才會完全準確） |
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

### 3.1 Phase 1 實作細節（與上方骨架的對應關係）

`src/strategy_engine.py` 對策略 dict 的實際讀取方式：

- `indicators`：list，每筆 `{"name","type","period","source","outputs"}`。`type` 支援 `SMA`/`EMA`/`RSI`/`MACD`/`ATR`/`ADX`/`BBANDS`；`MACD`/`BBANDS` 用 `outputs` 指定多個輸出變數名稱（不指定則用 `{name}_line` 等預設）。`ATR`/`ADX` 需要 price series 含 `high`/`low`，缺少時該股票會被排除而非拋例外（T1-3）。
- `derived_factors` / `filters` / `entry_signals` / `exit_signals`：每筆 `{"name"?, "expression"}`，`expression` 是字串運算式，透過 `src/expr.py` 的 `safe_eval()` 求值，變數來源為當日 OHLCV 欄位＋已計算指標＋前面已算出的 derived_factors。運算式只支援數字、變數、四則運算、比較與布林運算子，**不可**呼叫函式或存取任意 Python 物件。
- `universe.min_history_days`：低於此天數的股票直接視為資料不足，`evaluate_stock()` 回傳 `None`（對應 T1-3 新股情境）。
- `ranking.factor` / `ranking.order`：以某個因子（可以是指標或 derived_factor）排序，`rank_stocks()` 對輸入股票先依 stock_id 升冪排序再做穩定排序，確保同分時順序固定、同輸入必得同輸出（T1-4）。
- `portfolio.max_positions`：`rank_stocks()` 回傳結果會截斷到這個數量。

### 3.2 Phase 2 次日預測模組設計

`src/predictor.py` 採用可解釋的「排名分數延伸」模型，刻意不用黑箱模型：

- 輸入 `history: list[dict[stock_id, {"score": float}]]`，由舊到新排列的每日排名分數快照（實務上會是每天呼叫 `strategy_engine.rank_stocks()` 後整理出的 `{stock_id: {"score": ...}}`）。
- `predict_next_day(history, lookback=5, top_n=10)`：取最近 `lookback` 天，對每檔股票計算分數的平均日變化量（線性趨勢），外插出次日預測分數；`confidence`（0～100）＝過去變化方向與整體趨勢方向一致的比例，趨勢愈穩定信心度愈高。每筆預測都附 `basis`（最新分數、平均日變化、實際涵蓋天數），可回答「為什麼」。
- `walk_forward_backtest(daily_scores, lookback=5, top_n=10)`：逐日往前滾動，用第 t 天之前的 `lookback` 天預測第 t 天前 `top_n` 名，與第 t 天實際排名比對重疊率，回傳 `records`（每天一筆）與 `avg_overlap_rate`，供追蹤模型表現隨時間變化，不要求高準確率。
- 兩個函式輸出皆為純 dict/list，可直接 `json.dumps()`，供之後 Phase 3 併入 `report.json` 的「次日預測名單」欄位。

## 4. report.json 欄位定義（Model 規格）

完整 JSON Schema 見 `src/report_schema.py`（`REPORT_SCHEMA`），`src/report_builder.build_report()` 會在組裝時自動呼叫 `validate_report()`，不合規會直接拋出 `jsonschema.exceptions.ValidationError`。頂層欄位：

| 欄位 | 型別 | 說明 |
|---|---|---|
| `date` | string (`YYYY-MM-DD`) | 報告對應日期 |
| `generated_at` | string | ISO 8601 產生時間 |
| `cash` | object | `{amount, pct_of_total}` |
| `holdings` | array | 每筆：`stock_id, name, shares, cost_basis, current_price, market_value, pct_of_portfolio, unrealized_pnl_pct, pe_ratio, performance{1d_pct,1w_pct,1m_pct}` |
| `total_market_value` / `total_value` | number | 持股總市值／現金＋持股總資產 |
| `top10` | array | 每筆至少 `{stock_id, score}`，來自 `strategy_engine.rank_stocks()` |
| `predictions` | object | `{lookback, top_n, items: [{stock_id, predicted_score, confidence}]}`，來自 `predictor.predict_next_day()` |
| `watched_sectors` | array | 每筆 `{sector, representative_stocks[], today_pct_change}` |
| `nav_history` | array | 每筆 `{date, nav, drawdown_pct}` |

`src/portfolio.py` 負責產生 `cash`／`holdings`／`total_*`（對應 T3-1 的績效%計算）；`top10`／`predictions` 分別由 Phase 1／Phase 2 的模組產生後傳入 `build_report()`；`watched_sectors`／`nav_history` 目前由呼叫端自行組裝傳入，尚無獨立產生模組。

## 5. 目前進度

- **已完成**：Phase 0　資料源驗證 — **Gate 已通過**（使用者於本機 Windows + Python 3.12 執行 `scripts/verify_phase0.py` 驗證，2026-08-03）
  - T0-1（近一年日 K 線完整度）：2330／2317／0050 各 266 筆，日期連續無缺漏 — PASS
  - T0-2（財報欄位可用性）：2330／2317 的 EPS、Revenue、IncomeAfterTaxes、EquityAttributableToOwnersOfParent、PER 均可正確取得數值；0050 為 ETF，無公司財報／PER，驗證腳本已改為對 ETF 自動略過此項而非判定失敗 — PASS
  - T0-3（執行時間 < 5 分鐘）：實測 1.7 秒 — PASS
  - T0-4（資料源異常處理）：不存在的股票代號、連線失敗兩種情境皆正確回傳 `FetchResult(ok=False)`，未拋例外中斷流程 — PASS
  - 尚待人工確認：T0-2「財報數字與公開資訊誤差 < 1%」需對照公開來源核對 `phase0_snapshot.json` 數值（非阻斷性，非自動化項目）
- **已完成**：Phase 1　指標計算與策略引擎（JSON 驅動） — **程式與自動化測試已完成並於本 repo 沙箱內驗證通過（16/16 pytest）**，2026-08-03
  - T1-1（指標計算正確性）：`tests/test_indicators.py` 以已知範例資料／獨立手算公式驗證 SMA/EMA/RSI/MACD/ATR/BBANDS/ADX，含邊界情況（全漲/全跌/資料不足/價格不變）— PASS（自動化部分）。**與 TradingView/XQ 即時比對誤差 <0.5% 這部分需要真實即時資料，此開發環境無網路無法做，待有網路環境時人工比對**
  - T1-2（換策略 JSON 排名隨之改變、不需改程式碼）：`test_t1_2_swapping_strategy_json_changes_ranking` 用同一份 universe 分別套用 `strategy_momentum.json` 與 `strategy_meanreversion.json`，排名結果不同 — PASS
  - T1-3（極端情況正確排除、不崩潰）：新股上市未滿 260 日、缺 high/low 導致 ATR 無法計算、空 universe，三種情境皆正確回傳空結果或排除該股票而非拋例外 — PASS
  - T1-4（結果可重現性）：同一天同一份資料重跑兩次，`rank_stocks()` 結果完全相同（含 float 分數）— PASS
  - Gate 要求「至少 2 份不同策略 JSON 的獨立測試」：已用 `strategy_momentum.json`／`strategy_meanreversion.json` 兩份達成
- **已完成**：Phase 2　次日預測模組 — **程式與自動化測試完成，7/7 pytest 通過（全套 23/23）**，2026-08-03
  - T2-1（walk-forward 回測，重疊率有紀錄可追蹤）：`walk_forward_backtest()` 對 70 天合成資料逐日滾動預測，`records` 長度、`overlap_rate` 範圍、`overlap_count` 與實際交集皆驗證正確；非要求高準確率 — PASS
  - T2-2（信心度需在 0～100 合理區間）：`test_t2_2_confidence_within_valid_range` 驗證所有預測 `confidence` 落在 [0,100] — PASS
  - T2-3（輸出格式符合 Model 規格、可被 Dashboard/Email 讀取）：`predict_next_day()`／`walk_forward_backtest()` 輸出皆為純 dict/list，`json.dumps()`／`json.loads()` 往返驗證通過，欄位固定為 `stock_id`/`predicted_score`/`confidence`/`basis` — PASS
  - Gate（預測模組輸出格式與回測紀錄機制驗證通過）：達成
- **已完成**：Phase 3　報告 Model 產生與歷史儲存 — **程式與自動化測試完成，17/17 pytest 通過（全套 39/39）**，2026-08-03
  - T3-1（手動輸入持倉，1日/1週/1月績效% 與人工試算一致）：`test_t3_1_performance_matches_manual_calculation` 用等差數列收盤價，與獨立手算的報酬率公式比對一致 — PASS
  - T3-2（連續 5 天報告不互相覆蓋）：`test_t3_2_five_consecutive_days_produce_independent_reports` 對 5 個不同日期各自 `save_report()`，5 個 `reports/YYYY-MM-DD/` 資料夾各自獨立、內容對應各自日期 — PASS。另外驗證「同一天重複儲存」正確覆蓋當天而不新增資料夾
  - T3-3（report.json 通過 JSON Schema 驗證）：`src/report_schema.py` 定義完整 Schema，`build_report()` 組裝時自動驗證；測試涵蓋合法報告通過、缺必填欄位的報告正確拋出 `ValidationError` — PASS
  - T3-4（新資金匯入／跨月再平衡正確觸發且僅觸發一次）：`src/rebalance.py` 的 `run_rebalance_calendar()` 通過 6 種情境測試，包含「同一天同時符合兩個觸發條件仍只觸發一次」「同月配額不因呼叫端重複標記而重複觸發」「跨月後配額正常重置」— PASS
  - Gate（連續 5 天報告資料正確性人工抽查通過）：自動化測試已驗證程式邏輯正確（含當時用合成資料的初版驗證），**後續補上整合腳本後已用合成資料重跑一次完整 5 天流程確認不互相污染，但仍未用真實 FinMind 資料跑過**，見下方已知限制
- **已完成（Phase 3 收尾）**：每日整合腳本 `scripts/daily_pipeline.py` — 補上原本 Phase 3 進度記錄的缺口，2026-08-03
  - 新增 `src/nav.py`（NAV／回撤，狀態跨日持久化）、`src/score_history.py`（排名分數多日滾動快照，接給 predictor 用）、`src/sectors.py`（關注類股當日表現）
  - `src/strategy_engine.rank_stocks()` 新增 `apply_position_limit` 參數，可回傳全部候選股分數（不只 `max_positions` 檔），供分數歷史累積使用；預設行為不變，Phase 1 測試仍全數通過
  - `run_pipeline()`（純函式，不碰網路/檔案）把 rank_stocks → score_history → predictor → portfolio → sectors → nav → rebalance → report_builder 串成一次執行；`main()` 負責讀 `config/` 設定、呼叫 FinMind、寫入 `reports/`
  - `config/universe.json`（30 檔精選候選股）、`config/watched_sectors.json`（依使用者指示：半導體/AI/金融）、`config/holdings.json`（空白預設值，待使用者填入真實持股；含 `new_cash_inflow_today` 手動旗標取代不可靠的自動推斷）
  - `tests/test_daily_pipeline.py` 用合成資料驗證：單次執行產生合規 report.json、連續 5 天 `nav_history` 正確逐日累積且各天報告不互相污染、只有當月第一個交易日觸發再平衡、資金匯入日單獨觸發、缺價格資料的股票被優雅排除不中斷流程 — 4 項全過（全套累計 58/58）
  - `.github/workflows/daily-pipeline.yml`：手動觸發執行整合腳本並把 `reports/` 的變更 commit 回 repo
- **已完成（隱私架構調整）**：完整版／公開版報告分離 — 2026-08-03，因應使用者「repo 之後要公開以便用 GitHub Pages 架 Dashboard，但真實持股不能外流」的決定
  - `src/report_schema.py` 新增 `PUBLIC_REPORT_SCHEMA`、`build_public_report()`、`validate_public_report()`
  - `src/report_builder.py` 新增 `save_public_report()`／`load_public_report()`／`public_report_path()`，完整版與公開版分別寫入 `reports/` 與 `reports_public/`
  - `.gitignore` 排除 `config/holdings.json`、`reports/*/`、`reports/nav_state.json`、`reports/rebalance_state.json`；`config/holdings.json` 已用 `git rm --cached` 從版控移除
  - `daily_pipeline.py` 的 `main()` 同時寫出兩個版本；workflow 改為只 commit `reports_public/` 與 `reports/score_history.json`（分數歷史不含金額，可公開），並新增從 `HOLDINGS_JSON` Secret 寫入持股設定的步驟
  - `tests/test_public_report.py` 5 項測試：確認公開版拿掉 `cash.amount`／`shares`／`cost_basis`／`current_price`／`market_value`／`total_market_value`／`total_value`，保留佔比%／損益%／績效%／排名／預測／NAV，通過自己的 Schema，且用字串比對確保檔案內容真的找不到任何金額數字（防止日後新增欄位時漏改）
  - 全套測試 63/63 通過
- **已完成（第一筆真實資料）**：2026-08-03，使用者在本機 Windows + Python 3.12 執行 `daily_pipeline.py`，成功產生 2026-07-31 的真實報告
  - 用 `scripts/convert_holdings_csv.py` 把富邦成交紀錄 CSV（Big5 編碼、移動平均法算成本）轉出 22 檔佔比 >= 1% 的持股，寫入本機 `config/holdings.json`
  - `reports/2026-07-31/report.json`（完整版）人工核對：22 檔持股、股數、成本、市值、損益% 皆正確；`cash` 目前仍是 0（使用者尚未填交割戶餘額，待補）
  - `git status` 確認只有 `reports_public/2026-07-31/report.json`、`reports/score_history.json` 兩個安全檔案被 staged，完整版與 `holdings.json` 皆未被 git 追蹤，commit `b6588dc` 推上 `claude/github-login-o83wwg`
  - **T3-2／T3-4 的 Gate 首次用真實資料跑通**（目前只有一天，跨日不互污染需之後累積更多天數觀察，但單日流程與資料正確性已確認）
- **進行中**：無，等待使用者決定要不要補 `cash` 金額、之後想繼續 Phase 4（Dashboard）
- **已知限制**：
  - 開發用雲端 sandbox 連不到 `api.finmindtrade.com`，此限制會持續影響後續所有 Phase 的資料驗證，皆須在 GitHub Actions 或使用者本機執行後回報結果
  - `requirements.txt` / `requirements-broker.txt` 曾因檔案內中文註解，在 Windows 繁體中文語系（cp950）下被 `pip install -r` 讀取時噴 `UnicodeDecodeError`，已改為純英文註解修正；日後新增 requirements 檔案應避免非 ASCII 字元
  - `src/strategy_engine.py` 目前只計算「最新一筆」因子值（適合每日排名/報告用途），尚未支援對整段歷史序列逐日計算因子（回測 Phase 需要時要再擴充）
  - `config/holdings.json` 的 `cash` 目前是 0（使用者還沒填交割戶實際餘額），`total_value`／`cash.pct_of_total` 因此還不完全準確，待使用者自行更新後重跑
  - **跨日狀態在 GitHub Actions 上無法累積**（見 1.1 節末段）：`nav_state.json`／`rebalance_state.json` 不進 git，Actions 每次執行都是全新環境，NAV 會重新從 1.0 開始、再平衡狀態重置。目前只有本機連續執行能正確累積，這個缺口尚未解決——**代表現階段建議使用者固定在同一台本機每天手動或排程執行 `daily_pipeline.py`，而不是依賴 GitHub Actions 自動排程**
  - `daily_pipeline.py` 的 `is_first_trading_day_of_month` 判斷依賴 `0050` 的日期序列做市場交易日曆，若 `0050` 抓取失敗會直接中止整批執行（`main()` 已對此情況印出錯誤訊息並回傳非 0 結束碼，不會產生半殘的報告）
  - `config/universe.json` 是精選 30 檔，非全市場；之後想擴大選股範圍只需編輯這份 JSON，不需要改程式碼
  - 使用者的實際持股共 245 檔（多為 1～2 股零股），`convert_holdings_csv.py` 預設用 1% 成本佔比門檻篩選後保留 22 檔；門檻可用 `--min-pct` 調整

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
- 2026-08-03：完成 Phase 1（`src/indicators.py`、`src/expr.py`、`src/strategy_engine.py`、兩份範例策略 JSON、`tests/test_indicators.py`、`tests/test_strategy_engine.py`、`.github/workflows/phase1-test.yml`）。16 項 pytest 全數通過，涵蓋 T1-2／T1-3／T1-4 自動化驗證；T1-1 的指標公式正確性以獨立手算/已知範例驗證通過，但與 TradingView/XQ 的即時比對需要真實網路資料，待有連線環境時人工核對。**Phase 1 自動化部分 Gate 通過，進入 Phase 2**。
- 2026-08-03：完成 Phase 2（`src/predictor.py`：`predict_next_day()` 以排名分數線性趨勢外插預測、`walk_forward_backtest()` 逐日滾動回測記錄重疊率；`tests/test_predictor.py`）。純運算、不需外部資料源，7 項 pytest 於此開發環境直接驗證通過（全套累計 23/23）。`.github/workflows/phase1-test.yml` 更名為 `unit-tests.yml`，沿用同一個 workflow 涵蓋 Phase 1＋2 測試。**Phase 2 Gate 通過，進入 Phase 3**。
- 2026-08-03：完成 Phase 3（`src/portfolio.py`、`src/rebalance.py`、`src/report_schema.py`、`src/report_builder.py`，新增 `jsonschema` 相依套件；`tests/test_portfolio.py`、`tests/test_report_builder.py`、`tests/test_rebalance.py`）。17 項 pytest 全數通過（全套累計 39/39），涵蓋 T3-1～T3-4 自動化驗證。**這輪驗證用的是測試建構的範例資料，不是真實 5 個交易日的 FinMind 資料**——因為目前還沒有把 Phase 0～3 的模組串成一支「每日整合腳本」定時產生真實 report.json，這是接下來的已知缺口，計劃在 Phase 4 建 Dashboard 前補上，屆時要用真實資料重跑一次 T3-2／T3-4 才能算完整通過 Gate。`watched_sectors` 需要的「三大關注類股」清單也還沒跟使用者確認。**Phase 3 自動化部分 Gate 通過，進入 Phase 4**。
- 2026-08-03：使用者確認關注類股為半導體／AI／金融，並要求先補齊每日整合腳本再進 Phase 4。新增 `src/nav.py`、`src/score_history.py`、`src/sectors.py`（各自測試）、`scripts/daily_pipeline.py`（`run_pipeline()` 純函式串接所有 Phase 0～3 模組）、`tests/test_daily_pipeline.py`（合成資料驗證單次執行與連續 5 天不互污染）、`config/universe.json`／`holdings.json`／`holdings.example.json`／`watched_sectors.json`、`.github/workflows/daily-pipeline.yml`（手動觸發＋自動 commit `reports/`）。`strategy_engine.rank_stocks()` 新增 `apply_position_limit` 參數（向後相容，Phase 1 測試不受影響）。22 項新測試全數通過（全套累計 58/58）。**`reports/` 目錄目前仍是空的**：`config/holdings.json` 是空白預設值，且這支整合腳本尚未用真實 FinMind 資料實際跑過，待使用者於 GitHub Actions 手動觸發 `daily-pipeline.yml` 或本機執行後回報結果，才能算完整驗證 T3-2／T3-4 的 Gate。
- 2026-08-03：使用者提供富邦匯出的「庫存」與「成交紀錄」CSV（Big5 編碼）。庫存檔沒有成本欄位，改用成交紀錄以移動平均法回推各檔剩餘股數與平均成本，寫成 `scripts/convert_holdings_csv.py`；實測 245 檔持股中依 1% 成本佔比門檻篩選後保留 22 檔較大部位。
- 2026-08-03：使用者確認 repo 之後要改成**公開**（GitHub Pages 免費方案只支援公開 repo），因此新增完整版／公開版報告分離機制：`report_schema.build_public_report()` 去除所有絕對金額欄位、`report_builder.save_public_report()` 寫入 `reports_public/`，`.gitignore` 排除 `config/holdings.json` 與 `reports/` 下的完整版報告與狀態檔（`config/holdings.json` 已 `git rm --cached`），workflow 改為只 commit 公開版並支援用 `HOLDINGS_JSON` Secret 注入持股。新增 `tests/test_public_report.py` 5 項測試（全套 63/63）。**仍未解決**：`nav_state.json`／`rebalance_state.json` 跨日狀態無法在 GitHub Actions 執行之間保留，純雲端排程會讓 NAV 每次從 1.0 重來，見 1.1 節。
- 2026-08-03：**第一次真實資料端到端跑通**。使用者用 `convert_holdings_csv.py` 轉出的 22 檔持股填入本機 `config/holdings.json`，執行 `py -3.12 scripts/daily_pipeline.py` 成功產生 2026-07-31 的完整版與公開版報告；完整版經人工核對持股/市值/損益% 皆正確（`cash` 待補）。確認 `git status` 只會 commit `reports_public/2026-07-31/report.json` 與 `reports/score_history.json` 兩個不含金額的安全檔案後，commit `b6588dc` 推上 `claude/github-login-o83wwg`。至此 Phase 0～3（含每日整合腳本與隱私架構）全部有真實資料驗證過，可以開始 **Phase 4：GitHub Pages Dashboard**。
