"""state_sync.py 測試：用假的 requests.get/put 攔截，確保不會真的打 GitHub API。"""

import base64
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.state_sync import pull_state, push_state


class FakeResponse:
    def __init__(self, status_code: int, json_data: dict | None = None, text: str = ""):
        self.status_code = status_code
        self._json_data = json_data
        self.text = text

    def json(self):
        return self._json_data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}: {self.text}")


class FakeSession:
    """記錄呼叫，讓測試可以檢查有沒有帶正確的 header／body。"""

    def __init__(self, get_responses: list[FakeResponse], put_responses: list[FakeResponse] | None = None):
        self.get_responses = list(get_responses)
        self.put_responses = list(put_responses or [])
        self.get_calls = []
        self.put_calls = []

    def get(self, url, headers=None, timeout=None):
        self.get_calls.append({"url": url, "headers": headers, "timeout": timeout})
        return self.get_responses.pop(0)

    def put(self, url, headers=None, json=None, timeout=None):
        self.put_calls.append({"url": url, "headers": headers, "json": json, "timeout": timeout})
        return self.put_responses.pop(0)


def make_content_response(data: dict, sha: str = "abc123") -> FakeResponse:
    encoded = base64.b64encode(json.dumps(data).encode("utf-8")).decode("ascii")
    return FakeResponse(200, {"content": encoded, "sha": sha})


def test_pull_state_returns_none_when_file_missing(monkeypatch):
    fake = FakeSession(get_responses=[FakeResponse(404)])
    monkeypatch.setattr("src.state_sync.requests.get", fake.get)

    result = pull_state("owner/repo", "nav_state.json", "tok")
    assert result is None


def test_pull_state_decodes_base64_json(monkeypatch):
    data = {"baseline_total_value": 165607.5, "peak_nav": 1.05}
    fake = FakeSession(get_responses=[make_content_response(data)])
    monkeypatch.setattr("src.state_sync.requests.get", fake.get)

    result = pull_state("owner/repo", "nav_state.json", "tok")
    assert result == data
    assert fake.get_calls[0]["headers"]["Authorization"] == "Bearer tok"


def test_push_state_creates_file_when_missing(monkeypatch):
    fake = FakeSession(
        get_responses=[FakeResponse(404)],  # _get_file_sha 查不到 -> 視為新建
        put_responses=[FakeResponse(200, {})],
    )
    monkeypatch.setattr("src.state_sync.requests.get", fake.get)
    monkeypatch.setattr("src.state_sync.requests.put", fake.put)

    push_state("owner/repo", "nav_state.json", "tok", {"baseline_total_value": 1000.0})

    assert len(fake.put_calls) == 1
    body = fake.put_calls[0]["json"]
    assert "sha" not in body
    decoded = json.loads(base64.b64decode(body["content"]))
    assert decoded == {"baseline_total_value": 1000.0}


def test_push_state_updates_existing_file_with_sha(monkeypatch):
    fake = FakeSession(
        get_responses=[FakeResponse(200, {"content": "e30=", "sha": "existing-sha"})],
        put_responses=[FakeResponse(200, {})],
    )
    monkeypatch.setattr("src.state_sync.requests.get", fake.get)
    monkeypatch.setattr("src.state_sync.requests.put", fake.put)

    push_state("owner/repo", "nav_state.json", "tok", {"baseline_total_value": 2000.0})

    body = fake.put_calls[0]["json"]
    assert body["sha"] == "existing-sha"


def test_push_state_raises_on_http_error(monkeypatch):
    fake = FakeSession(
        get_responses=[FakeResponse(404)],
        put_responses=[FakeResponse(403, {}, text="Forbidden")],
    )
    monkeypatch.setattr("src.state_sync.requests.get", fake.get)
    monkeypatch.setattr("src.state_sync.requests.put", fake.put)

    with pytest.raises(RuntimeError):
        push_state("owner/repo", "nav_state.json", "tok", {"a": 1})
