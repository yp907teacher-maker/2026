# 2026

台股每日分析與通知系統：抓取公開行情、依策略 JSON 排名選股、產出每日報告、更新 Dashboard 並寄送 Email。

> 純資訊整理、排名計算與視覺化，**不構成投資建議，也不會自動下單**。實際交易由使用者自行在券商 App 操作。

## 架構

```
GitHub Actions（排程）
  → 抓取台股行情/財報（FinMind API）
  → 技術指標計算
  → 依 strategies/*.json 排名選股
  → 產生報告 JSON
  → GitHub Pages Dashboard 讀取顯示
  → 寄送 Email
```

## 目錄

| 路徑 | 說明 |
|---|---|
| `src/` | 核心程式：資料源、指標、策略引擎、投組/NAV、再平衡、報告產生、Email |
| `scripts/` | 執行入口，例如 `daily_pipeline.py`（每日流程）、`send_email.py` |
| `strategies/` | 策略設定（JSON），新增策略不需改 Python |
| `config/` | 投組、股票池、關注產業設定；`holdings.example.json` 為持股格式範例 |
| `dashboard/` | 純靜態 Dashboard（GitHub Pages） |
| `reports/` | 完整版報告與跨日狀態（含敏感資料，不進版控） |
| `reports_public/` | 公開版報告（僅百分比，無股數/成本/金額） |
| `tests/` | pytest 測試 |
| `fubon_client.py` | 富邦證券 API 查詢框架（獨立用途，下單功能停用） |
| `PROJECT_MEMORY.md` | 完整設計、決策與交接紀錄 |

## 安裝

需要 Python 3.12 左右。

```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt   # 開發/測試用
```

富邦 API（僅 Windows、選用）請見 `requirements-broker.txt` 內說明。

## 設定

```bash
cp .env.example .env
```

填入 `.env`（切勿提交）：

- `FINMIND_TOKEN`：可選，未填也能用但額度較低
- `SMTP_HOST` / `SMTP_PORT` / `SMTP_USER` / `SMTP_PASS` / `EMAIL_TO`：Email 通知；Gmail 請用「應用程式密碼」
- `FUBON_*`：僅在使用富邦持股同步時需要
- `STATE_REPO_TOKEN`：僅 GitHub Actions 需要

持股設定：複製 `config/holdings.example.json` 為 `config/holdings.json` 並填入實際持股（此檔已被 `.gitignore` 排除）。

## 使用

```bash
python scripts/daily_pipeline.py      # 執行每日流程
pytest                                # 執行測試
```

## 隱私

真實持股金額、股數、成本只存在完整版 `reports/`，不會進 git。公開版 `reports_public/` 只保留佔比與損益%，可安全公開。詳見 `PROJECT_MEMORY.md` 第 1.1 節。
