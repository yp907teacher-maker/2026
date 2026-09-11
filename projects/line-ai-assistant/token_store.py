import os
import sqlite3
import time
import uuid
from contextlib import contextmanager

from cryptography.fernet import Fernet

DB_PATH = os.environ.get("TOKEN_STORE_PATH", "token_store.sqlite3")
STATE_TTL_SECONDS = 600


def _fernet() -> Fernet:
    key = os.environ["TOKEN_ENCRYPTION_KEY"]
    return Fernet(key.encode() if isinstance(key, str) else key)


@contextmanager
def _connect():
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS google_tokens (
                line_user_id TEXT PRIMARY KEY,
                encrypted_refresh_token BLOB NOT NULL,
                linked_at REAL NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS oauth_states (
                state TEXT PRIMARY KEY,
                line_user_id TEXT NOT NULL,
                created_at REAL NOT NULL
            )
            """
        )
        yield conn
        conn.commit()
    finally:
        conn.close()


def create_oauth_state(line_user_id: str) -> str:
    state = uuid.uuid4().hex
    with _connect() as conn:
        conn.execute(
            "DELETE FROM oauth_states WHERE created_at < ?",
            (time.time() - STATE_TTL_SECONDS,),
        )
        conn.execute(
            "INSERT INTO oauth_states (state, line_user_id, created_at) VALUES (?, ?, ?)",
            (state, line_user_id, time.time()),
        )
    return state


def consume_oauth_state(state: str) -> str | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT line_user_id, created_at FROM oauth_states WHERE state = ?",
            (state,),
        ).fetchone()
        if row is None:
            return None
        conn.execute("DELETE FROM oauth_states WHERE state = ?", (state,))
        line_user_id, created_at = row
        if time.time() - created_at > STATE_TTL_SECONDS:
            return None
        return line_user_id


def save_refresh_token(line_user_id: str, refresh_token: str) -> None:
    encrypted = _fernet().encrypt(refresh_token.encode())
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO google_tokens (line_user_id, encrypted_refresh_token, linked_at)
            VALUES (?, ?, ?)
            ON CONFLICT(line_user_id) DO UPDATE SET
                encrypted_refresh_token = excluded.encrypted_refresh_token,
                linked_at = excluded.linked_at
            """,
            (line_user_id, encrypted, time.time()),
        )


def get_refresh_token(line_user_id: str) -> str | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT encrypted_refresh_token FROM google_tokens WHERE line_user_id = ?",
            (line_user_id,),
        ).fetchone()
    if row is None:
        return None
    return _fernet().decrypt(row[0]).decode()


def delete_refresh_token(line_user_id: str) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM google_tokens WHERE line_user_id = ?", (line_user_id,))


def all_linked_user_ids() -> list[str]:
    with _connect() as conn:
        rows = conn.execute("SELECT line_user_id FROM google_tokens").fetchall()
    return [row[0] for row in rows]
