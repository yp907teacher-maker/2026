# LINE AI 助理

一個透過 LINE Messaging API 串接 Claude 的聊天機器人,同時可以幫每位使用者連結自己的
Google 日曆:直接用自然語言在 LINE 建立日曆事件,並每日/每週自動推播提醒。

這是獨立子專案,與本 repo 其他目錄(台股分析系統)沒有任何程式碼相依關係。

## 架構

```
LINE 使用者 → LINE Messaging API → /callback (Flask) → Claude API(結構化輸出:判斷是聊天還是要建立日曆事件)
                                                              ↓ 若為建立事件
                                                        Google Calendar API(使用該使用者自己的 OAuth 憑證)

GitHub Actions(每日/每週排程)→ POST /internal/send-reminders → 讀取每位使用者的日曆 → LINE Push Message
```

- `app.py`:Flask webhook,收發 LINE 訊息、Google OAuth callback、內部提醒觸發端點
- `calendar_intent.py`:用 Claude 結構化輸出,一次判斷「這則訊息是聊天還是要建立日曆事件」並抽取事件欄位
- `google_calendar.py`:Google OAuth 授權流程 + Calendar API(建立事件、查詢事件)
- `token_store.py`:每位 LINE 使用者的 Google refresh token,加密後存在本機 SQLite
- `reminders.py`:組出「今日行程」「本週重要行程」訊息並用 LINE Push API 發送
- 對話歷史目前僅存在記憶體(程式重啟即清空),沒有資料庫

## 使用方式(LINE 對話)

- 傳「**連結日曆**」:機器人回傳一個 Google 授權連結(10 分鐘內有效),點擊完成授權後即可使用
- 傳「**解除日曆**」:解除該使用者的 Google 日曆連結
- 已連結日曆後,直接用自然語言說「明天下午三點跟客戶開會」之類的話,機器人會自動建立日曆事件並回覆確認
- 其他訊息一律視為一般聊天,由 Claude 回覆
- 已連結日曆的使用者,每天早上會收到當日行程提醒,每週一早上會收到未來一週的重要行程提醒

## 設定步驟

### 1. LINE Messaging API

到 [LINE Developers Console](https://developers.line.biz/) 建立一個 Messaging API channel,
取得 `Channel secret` 與 `Channel access token`。

### 2. Google Cloud OAuth

1. 到 [Google Cloud Console](https://console.cloud.google.com/) 建立專案,啟用 **Google Calendar API**
2. 建立 OAuth 2.0 用戶端 ID(應用程式類型選 **Web application**)
3. 在「已授權的重新導向 URI」加入 `https://<你的網域>/google/callback`
4. 取得 `Client ID` 與 `Client secret`

### 3. 環境變數

複製 `.env.example` 為 `.env`,依註解說明填入所有變數。`TOKEN_ENCRYPTION_KEY` 用以下指令產生:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### 4. 安裝與本機啟動

```bash
pip install -r requirements.txt
python app.py
```

用 ngrok 等工具將本機 port 對外,並把:
- `https://<your-domain>/callback` 設定為 LINE channel 的 Webhook URL
- `https://<your-domain>/google/callback` 設定為 Google OAuth 用戶端的重新導向 URI(需與 `GOOGLE_REDIRECT_URI` 完全一致)

### 5. 部署

任何能跑 Flask 的環境(例如 Render、Railway、Cloud Run)都可以部署,記得:
- 環境變數設定與 `.env.example` 相同
- `TOKEN_STORE_PATH` 指向的 SQLite 檔案要放在**持久化磁碟**上;若部署環境的磁碟是每次重啟就清空
  (例如某些 serverless/免費方案),使用者連結的日曆會在重啟後失效,需要重新輸入「連結日曆」

### 6. 每日/每週提醒排程(GitHub Actions)

排程設定檔在 repo 根目錄的 `.github/workflows/line-ai-assistant-reminders.yml`(GitHub Actions
只會讀取 repo 根目錄下的 `.github/workflows/`,子專案資料夾放了也不會生效)。它只是個「鬧鐘」,
實際邏輯都在你部署的 Flask 伺服器裡執行。需要在 repo 設定兩個 GitHub Secrets:

- `LINE_AI_ASSISTANT_BASE_URL`:你部署後的網址(例如 `https://your-app.example.com`)
- `LINE_AI_ASSISTANT_INTERNAL_SECRET`:與 `.env` 裡的 `INTERNAL_REMINDER_SECRET` 相同的值

也可以在 GitHub Actions 頁面手動觸發(workflow_dispatch)測試 daily/weekly 兩種提醒。
