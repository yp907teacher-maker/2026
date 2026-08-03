"""跨執行環境的私人狀態同步。

`nav_state.json` 含真實金額基準值（`baseline_total_value`），不能進公開 repo，
但 GitHub Actions 每次執行都是全新環境、沒有本機硬碟可以持久化。這個模組把
狀態改存到另一個**私人 repo**（`yp907teacher-maker/2026-private-state`），
透過 GitHub Contents API 讀寫，讓排程執行之間也能正確累積 NAV 基準值。

需要一組有該私人 repo 寫入權限的 Personal Access Token（環境變數
`STATE_REPO_TOKEN`）。本機執行沒有設定這個環境變數時，呼叫端應該退回讀寫
本機檔案，行為與之前完全相同（見 scripts/daily_pipeline.py 的
_load_nav_state()／_save_nav_state()）。
"""

from __future__ import annotations

import base64
import json

import requests

API_BASE = "https://api.github.com"
DEFAULT_STATE_REPO = "yp907teacher-maker/2026-private-state"


def _headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def pull_state(repo: str, path: str, token: str) -> dict | None:
    """讀取私人 repo 裡的 JSON 檔案內容。檔案不存在（第一次執行）回傳 None。"""
    url = f"{API_BASE}/repos/{repo}/contents/{path}"
    resp = requests.get(url, headers=_headers(token), timeout=15)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    payload = resp.json()
    content = base64.b64decode(payload["content"]).decode("utf-8")
    return json.loads(content)


def _get_file_sha(repo: str, path: str, token: str) -> str | None:
    url = f"{API_BASE}/repos/{repo}/contents/{path}"
    resp = requests.get(url, headers=_headers(token), timeout=15)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json()["sha"]


def push_state(
    repo: str, path: str, token: str, data: dict, message: str = "chore: update state"
) -> None:
    """寫入/更新私人 repo 裡的 JSON 檔案，自動處理 create vs update 需要的 sha。"""
    sha = _get_file_sha(repo, path, token)
    url = f"{API_BASE}/repos/{repo}/contents/{path}"
    encoded = base64.b64encode(
        json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    ).decode("ascii")
    body = {"message": message, "content": encoded}
    if sha:
        body["sha"] = sha
    resp = requests.put(url, headers=_headers(token), json=body, timeout=15)
    resp.raise_for_status()
