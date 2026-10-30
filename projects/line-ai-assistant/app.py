import os

from dotenv import load_dotenv
from flask import Flask, abort, request
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    ApiClient,
    Configuration,
    MessagingApi,
    ReplyMessageRequest,
    TextMessage,
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent

import google_calendar
import reminders
import token_store
from calendar_intent import CalendarAwareAssistant

load_dotenv()

app = Flask(__name__)

configuration = Configuration(access_token=os.environ["LINE_CHANNEL_ACCESS_TOKEN"])
handler = WebhookHandler(os.environ["LINE_CHANNEL_SECRET"])
assistant = CalendarAwareAssistant()

LINK_COMMANDS = {"連結日曆", "連接日曆", "綁定日曆"}
UNLINK_COMMANDS = {"解除日曆", "取消連結", "解除連結"}


def _reply(reply_token: str, text: str) -> None:
    with ApiClient(configuration) as api_client:
        MessagingApi(api_client).reply_message(
            ReplyMessageRequest(reply_token=reply_token, messages=[TextMessage(text=text)])
        )


@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return "OK"


@app.route("/google/callback", methods=["GET"])
def google_callback():
    state = request.args.get("state", "")
    code = request.args.get("code", "")
    error = request.args.get("error")

    if error:
        return f"Google 授權失敗：{error}", 400

    line_user_id = token_store.consume_oauth_state(state)
    if not line_user_id:
        return "授權連結已失效，請回到 LINE 重新輸入「連結日曆」。", 400

    try:
        refresh_token = google_calendar.exchange_code_for_refresh_token(code, state)
    except Exception as exc:  # noqa: BLE001 - surface any OAuth failure to the user
        return f"Google 授權失敗：{exc}", 400

    token_store.save_refresh_token(line_user_id, refresh_token)
    return "Google 日曆已成功連結，可以回到 LINE 繼續使用了！"


@app.route("/internal/send-reminders", methods=["POST"])
def send_reminders():
    secret = request.headers.get("X-Internal-Secret", "")
    if secret != os.environ["INTERNAL_REMINDER_SECRET"]:
        abort(403)

    reminder_type = request.args.get("type") or (request.get_json(silent=True) or {}).get("type")
    if reminder_type == "daily":
        sent = reminders.send_daily_reminders()
    elif reminder_type == "weekly":
        sent = reminders.send_weekly_reminders()
    else:
        abort(400)

    return {"sent": sent}


@handler.add(MessageEvent, message=TextMessageContent)
def handle_text_message(event: MessageEvent):
    user_id = event.source.user_id
    text = event.message.text.strip()

    if text in LINK_COMMANDS:
        state = token_store.create_oauth_state(user_id)
        auth_url = google_calendar.build_auth_url(state)
        _reply(event.reply_token, f"請點以下連結授權 Google 日曆（10 分鐘內有效）：\n{auth_url}")
        return

    if text in UNLINK_COMMANDS:
        token_store.delete_refresh_token(user_id)
        _reply(event.reply_token, "已解除 Google 日曆連結。")
        return

    turn = assistant.interpret(user_id, text)

    if turn.intent == "create_event" and turn.start_datetime:
        refresh_token = token_store.get_refresh_token(user_id)
        if not refresh_token:
            _reply(event.reply_token, "你還沒有連結 Google 日曆，請先輸入「連結日曆」完成授權。")
            return
        try:
            google_calendar.create_event(
                refresh_token=refresh_token,
                title=turn.title or "（未命名事件）",
                start_iso=turn.start_datetime,
                end_iso=turn.end_datetime or turn.start_datetime,
                timezone=os.environ.get("CALENDAR_TIMEZONE", "Asia/Taipei"),
                location=turn.location,
                all_day=turn.all_day,
            )
        except Exception as exc:  # noqa: BLE001 - surface any Calendar API failure to the user
            _reply(event.reply_token, f"建立日曆事件失敗：{exc}")
            return

    _reply(event.reply_token, turn.reply_text)


if __name__ == "__main__":
    app.run(port=int(os.environ.get("PORT", 5000)))
