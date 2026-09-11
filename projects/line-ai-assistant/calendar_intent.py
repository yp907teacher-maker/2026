import os
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

import anthropic
from pydantic import BaseModel

MODEL = "claude-opus-5"
MAX_HISTORY_TURNS = 10  # user+assistant pairs kept per LINE user
TIMEZONE_NAME = os.environ.get("CALENDAR_TIMEZONE", "Asia/Taipei")

SYSTEM_PROMPT_TEMPLATE = """你是一位親切、簡潔的中文 LINE AI 助理，同時也負責幫使用者管理 Google 日曆，
回覆盡量精簡易懂，適合在 LINE 聊天視窗中閱讀。

現在時間是 {now}（時區 {timezone}）。

規則：
- 如果使用者的訊息是要「新增/建立/安排一個日曆事件或提醒」，將 intent 設為 "create_event"，
  並盡量從訊息中推斷出 title、start_datetime、end_datetime（ISO 8601 格式，含時區偏移，例如
  2026-09-10T15:00:00+08:00）。如果使用者沒有指定結束時間，預設抓開始時間 1 小時後。如果是
  全天事件（只提到日期沒提到時間），all_day 設為 true，start_datetime/end_datetime 只需日期
  部分（例如 2026-09-10）。reply_text 請用一句話覆述你將建立的事件內容，語氣自然。
- 如果訊息看起來想建立事件，但缺少建立事件所需的關鍵資訊（例如沒有日期），intent 一樣設為
  "create_event"，但 start_datetime 留空，reply_text 改為詢問使用者缺少的資訊（例如日期或時間）。
- 其他情況（一般聊天、問問題等）intent 設為 "chat"，title/start_datetime/end_datetime/location
  留空，reply_text 放正常的聊天回覆內容。
- reply_text 是唯一會顯示給使用者看的欄位，請務必用完整、自然的繁體中文撰寫。
"""


class AssistantTurn(BaseModel):
    intent: str  # "create_event" or "chat"
    title: Optional[str] = None
    start_datetime: Optional[str] = None  # ISO 8601, timezone-aware
    end_datetime: Optional[str] = None  # ISO 8601, timezone-aware
    all_day: bool = False
    location: Optional[str] = None
    reply_text: str


class CalendarAwareAssistant:
    """Routes each LINE message to either a calendar-event extraction or a
    plain chat reply, via a single structured-output Claude call per turn."""

    def __init__(self):
        self._client = anthropic.Anthropic()
        self._histories: dict[str, list[dict]] = {}

    def _system_prompt(self) -> str:
        now = datetime.now(ZoneInfo(TIMEZONE_NAME)).isoformat()
        return SYSTEM_PROMPT_TEMPLATE.format(now=now, timezone=TIMEZONE_NAME)

    def interpret(self, user_id: str, user_message: str) -> AssistantTurn:
        history = self._histories.setdefault(user_id, [])
        history.append({"role": "user", "content": user_message})

        response = self._client.messages.parse(
            model=MODEL,
            max_tokens=1024,
            system=self._system_prompt(),
            messages=history,
            output_format=AssistantTurn,
        )
        turn = response.parsed_output

        history.append({"role": "assistant", "content": turn.reply_text})

        excess = len(history) - MAX_HISTORY_TURNS * 2
        if excess > 0:
            del history[:excess]

        return turn
