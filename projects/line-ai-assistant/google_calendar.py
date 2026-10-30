import os
from datetime import datetime

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/calendar.events"]
TOKEN_URI = "https://oauth2.googleapis.com/token"
AUTH_URI = "https://accounts.google.com/o/oauth2/auth"


def _client_config() -> dict:
    return {
        "web": {
            "client_id": os.environ["GOOGLE_CLIENT_ID"],
            "client_secret": os.environ["GOOGLE_CLIENT_SECRET"],
            "auth_uri": AUTH_URI,
            "token_uri": TOKEN_URI,
            "redirect_uris": [os.environ["GOOGLE_REDIRECT_URI"]],
        }
    }


def build_auth_url(state: str) -> str:
    flow = Flow.from_client_config(_client_config(), scopes=SCOPES, state=state)
    flow.redirect_uri = os.environ["GOOGLE_REDIRECT_URI"]
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    return auth_url


def exchange_code_for_refresh_token(code: str, state: str) -> str:
    flow = Flow.from_client_config(_client_config(), scopes=SCOPES, state=state)
    flow.redirect_uri = os.environ["GOOGLE_REDIRECT_URI"]
    flow.fetch_token(code=code)
    refresh_token = flow.credentials.refresh_token
    if not refresh_token:
        raise ValueError(
            "Google 未回傳 refresh_token，請確認這是使用者第一次同意授權"
            "（Google 只有在第一次同意，或撤銷後重新授權時才會核發）"
        )
    return refresh_token


def _credentials_from_refresh_token(refresh_token: str) -> Credentials:
    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri=TOKEN_URI,
        client_id=os.environ["GOOGLE_CLIENT_ID"],
        client_secret=os.environ["GOOGLE_CLIENT_SECRET"],
        scopes=SCOPES,
    )
    creds.refresh(Request())
    return creds


def _calendar_service(refresh_token: str):
    creds = _credentials_from_refresh_token(refresh_token)
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


def create_event(
    refresh_token: str,
    title: str,
    start_iso: str,
    end_iso: str,
    timezone: str,
    location: str | None = None,
    all_day: bool = False,
) -> str:
    service = _calendar_service(refresh_token)

    if all_day:
        time_fields = {
            "start": {"date": start_iso[:10]},
            "end": {"date": end_iso[:10]},
        }
    else:
        time_fields = {
            "start": {"dateTime": start_iso, "timeZone": timezone},
            "end": {"dateTime": end_iso, "timeZone": timezone},
        }

    event = {"summary": title, **time_fields}
    if location:
        event["location"] = location

    created = service.events().insert(calendarId="primary", body=event).execute()
    return created.get("htmlLink", "")


def list_events(
    refresh_token: str, time_min: datetime, time_max: datetime, timezone: str
) -> list[dict]:
    service = _calendar_service(refresh_token)
    result = (
        service.events()
        .list(
            calendarId="primary",
            timeMin=time_min.isoformat(),
            timeMax=time_max.isoformat(),
            singleEvents=True,
            orderBy="startTime",
            timeZone=timezone,
        )
        .execute()
    )
    return result.get("items", [])
