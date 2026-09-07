# LINE AI 助理

一個透過 LINE Messaging API 串接 Claude 的聊天機器人。使用者在 LINE 傳訊息給官方帳號，
Flask webhook 收到後轉交 Claude API 產生回覆，再回傳到 LINE 對話視窗。

這是獨立子專案，與本 repo 其他目錄（台股分析系統）沒有任何程式碼相依關係。

## 架構

```
LINE 使用者 → LINE Messaging API → /callback (Flask) → Claude API → 回覆訊息
```

- `app.py`：Flask webhook，驗證 LINE 簽章、收發訊息
- `claude_client.py`：包裝 Claude API 呼叫，並在記憶體中保留每位使用者的簡短對話歷史
- 對話歷史目前僅存在記憶體（程式重啟即清空），沒有資料庫

## 設定步驟

1. 到 [LINE Developers Console](https://developers.line.biz/) 建立一個 Messaging API channel，
   取得 `Channel secret` 與 `Channel access token`。
2. 複製 `.env.example` 為 `.env`，填入：
   - `LINE_CHANNEL_SECRET`
   - `LINE_CHANNEL_ACCESS_TOKEN`
   - `ANTHROPIC_API_KEY`（若本機已用 `ant auth login` 登入可省略）
3. 安裝相依套件：
   ```bash
   pip install -r requirements.txt
   ```
4. 本機啟動：
   ```bash
   python app.py
   ```
5. 用 ngrok 等工具將本機 port 對外，並把 `https://<your-domain>/callback`
   設定為 LINE channel 的 Webhook URL。

## 部署

任何能跑 Flask 的環境（例如 Render、Railway、Cloud Run）都可以部署，
記得在環境變數中設定與 `.env.example` 相同的三個變數。
