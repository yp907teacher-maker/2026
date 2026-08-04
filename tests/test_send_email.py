"""send_email.py 測試：對應 T5-1（能正確寄出）、T5-4（讀取 warnings.json）。

用假的 smtplib.SMTP_SSL 攔截，確保測試不會真的連網路寄信。
"""

import base64
import json
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.send_email import latest_report_date, load_warnings, send_email


class FakeSMTP:
    instances = []

    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.login_args = None
        self.sendmail_args = None
        FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def login(self, user, password):
        self.login_args = (user, password)

    def sendmail(self, from_addr, to_addrs, message):
        self.sendmail_args = (from_addr, to_addrs, message)


@pytest.fixture(autouse=True)
def clear_fake_instances():
    FakeSMTP.instances.clear()
    yield
    FakeSMTP.instances.clear()


@pytest.fixture
def tmp_reports_dir():
    d = tempfile.mkdtemp()
    yield Path(d)
    shutil.rmtree(d, ignore_errors=True)


def make_minimal_report(date: str = "2026-08-03") -> dict:
    return {
        "date": date,
        "generated_at": f"{date}T06:00:00+08:00",
        "cash": {"amount": 1000.0, "pct_of_total": 1.0},
        "holdings": [],
        "total_market_value": 0.0,
        "total_value": 1000.0,
        "top10": [],
        "predictions": {"lookback": 5, "top_n": 10, "items": []},
        "watched_sectors": [],
        "nav_history": [{"date": date, "nav": 1.0, "drawdown_pct": 0.0}],
        "benchmark_nav_history": [{"date": date, "nav": 1.0}],
        "rebalance": {"triggered": False, "reason": None},
    }


def test_t5_1_send_email_calls_smtp_with_expected_args(monkeypatch):
    monkeypatch.setattr("scripts.send_email.smtplib.SMTP_SSL", FakeSMTP)

    report = make_minimal_report()
    env = {
        "SMTP_HOST": "smtp.example.com",
        "SMTP_PORT": "465",
        "SMTP_USER": "bot@example.com",
        "SMTP_PASS": "app-password",
        "EMAIL_TO": "me@example.com",
    }

    send_email(report, warnings=[], env=env)

    assert len(FakeSMTP.instances) == 1
    smtp = FakeSMTP.instances[0]
    assert smtp.host == "smtp.example.com"
    assert smtp.port == 465
    assert smtp.login_args == ("bot@example.com", "app-password")

    from_addr, to_addrs, message = smtp.sendmail_args
    assert from_addr == "bot@example.com"
    assert to_addrs == ["me@example.com"]

    # HTML 內容以 base64 附在信件本體裡，解碼後確認真的是這份報告的內容
    b64_body = message.split("Content-Transfer-Encoding: base64\n\n", 1)[1].split("\n--")[0]
    decoded_html = base64.b64decode(b64_body).decode("utf-8")
    assert "2026-08-03" in decoded_html


def test_latest_report_date_picks_max(tmp_reports_dir):
    (tmp_reports_dir / "2026-08-01").mkdir()
    (tmp_reports_dir / "2026-08-03").mkdir()
    (tmp_reports_dir / "2026-08-02").mkdir()
    assert latest_report_date(tmp_reports_dir) == "2026-08-03"


def test_latest_report_date_none_when_missing(tmp_reports_dir):
    empty_dir = tmp_reports_dir / "does-not-exist"
    assert latest_report_date(empty_dir) is None


def test_latest_report_date_ignores_portfolio_subdirectories(tmp_reports_dir):
    """Phase 6 之後 reports/ 底下除了日期資料夾，還會有非 default 組合的子目錄
    （例如 reports/example_meanreversion/），這種目錄名不能被誤判成日期。"""
    (tmp_reports_dir / "2026-08-03").mkdir()
    (tmp_reports_dir / "example_meanreversion").mkdir()
    assert latest_report_date(tmp_reports_dir) == "2026-08-03"


def test_t5_4_load_warnings_returns_empty_list_when_no_file(tmp_reports_dir):
    (tmp_reports_dir / "2026-08-03").mkdir()
    assert load_warnings("2026-08-03", tmp_reports_dir) == []


def test_t5_4_load_warnings_reads_existing_file(tmp_reports_dir):
    day_dir = tmp_reports_dir / "2026-08-03"
    day_dir.mkdir()
    warnings = ["2454 資料抓取失敗，未列入今日排名/預測"]
    with open(day_dir / "warnings.json", "w", encoding="utf-8") as fh:
        json.dump(warnings, fh, ensure_ascii=False)

    assert load_warnings("2026-08-03", tmp_reports_dir) == warnings
