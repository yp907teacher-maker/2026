import os
import threading

import anthropic

MODEL = "claude-opus-5"
MAX_HISTORY_TURNS = 10  # user+assistant pairs kept per LINE user

DEFAULT_SYSTEM_PROMPT = (
    "你是一位親切、簡潔的中文 AI 助理，回覆盡量精簡易懂，"
    "適合在 LINE 聊天視窗中閱讀。"
)


class ClaudeAssistant:
    """Stateless-per-call wrapper around the Claude API with a small
    in-memory conversation history per LINE user."""

    def __init__(self):
        self._client = anthropic.Anthropic()
        self._system_prompt = os.environ.get(
            "ASSISTANT_SYSTEM_PROMPT", DEFAULT_SYSTEM_PROMPT
        )
        self._histories: dict[str, list[dict]] = {}
        self._lock = threading.Lock()

    def reply(self, user_id: str, user_message: str) -> str:
        with self._lock:
            history = self._histories.setdefault(user_id, [])
            history.append({"role": "user", "content": user_message})

            response = self._client.messages.create(
                model=MODEL,
                max_tokens=1024,
                system=self._system_prompt,
                messages=history,
            )

            reply_text = next(
                (block.text for block in response.content if block.type == "text"),
                "",
            )
            history.append({"role": "assistant", "content": reply_text})

            # Keep only the most recent turns to bound memory/cost.
            excess = len(history) - MAX_HISTORY_TURNS * 2
            if excess > 0:
                del history[:excess]

            return reply_text or "抱歉，我暫時無法回覆這則訊息。"
