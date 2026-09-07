import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from linebot.v3.messaging import (
    ApiClient,
    Configuration,
    MessagingApi,
    PushMessageRequest,
    TextMessage,
)

import google_calendar
import token_store

TIMEZONE_NAME = os.environ.get("CALENDAR_TIMEZONE", "Asia/Taipei")


def format_events(events: list[dict], tz: ZoneInfo) -> str:
    if not events:
        return "目前沒有排定的行程。"

    lines = []
    for event in events:
        title = event.get("summary", "（未命名事件）")
        start = event.get("start", {})
        start_value = start.get("dateTime") or start.get("date")
        if start_value is None:
            continue
        if "T" in start_value:
            dt = datetime.fromisoformat(start_value).astimezone(tz)
            lines.append(f"・{dt.strftime('%m/%d %H:%M')} {title}")
        else:
            lines.append(f"・{start_value}（全天）{title}")
    return "\n".join(lines)


def _push(line_user_id: str, text: str) -> None:
    configuration = Configuration(access_token=os.environ["LINE_CHANNEL_ACCESS_TOKEN"])
    with ApiClient(configuration) as api_client:
        MessagingApi(api_client).push_message(
            PushMessageRequest(to=line_user_id, messages=[TextMessage(text=text)])
        )


def _send_for_window(header: str, days_ahead: int) -> int:
    tz = ZoneInfo(TIMEZONE_NAME)
    now = datetime.now(tz)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=days_ahead)

    sent = 0
    for user_id in token_store.all_linked_user_ids():
        refresh_token = token_store.get_refresh_token(user_id)
        if not refresh_token:
            continue
        events = google_calendar.list_events(refresh_token, start, end, TIMEZONE_NAME)
        _push(user_id, f"{header}\n{format_events(events, tz)}")
        sent += 1
    return sent


def send_daily_reminders() -> int:
    return _send_for_window("📅 今日行程", days_ahead=1)


def send_weekly_reminders() -> int:
    return _send_for_window("📆 本週重要行程", days_ahead=7)
