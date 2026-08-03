"""每日 Email 通知：讀取 reports/{date}/report.json（完整版）渲染成 HTML Email 並寄出。

Model/View 分離：這支腳本不重新計算任何資料，只讀 daily_pipeline.py 已經產生好的
report.json 來渲染，跟 Dashboard 共用同一份 Model，各自是獨立的 View。

寄信設定透過環境變數（本機可寫在 .env，GitHub Actions 用 Secrets）：
    SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, EMAIL_TO
Gmail 使用者請用「應用程式密碼」當 SMTP_PASS，一般登入密碼無法用於 SMTP。

用法：
    python scripts/send_email.py [YYYY-MM-DD]
不帶日期參數時，寄出 reports/ 底下最新一天的報告。
"""

from __future__ import annotations

import json
import os
import smtplib
import sys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv  # noqa: E402

from src.email_report import build_email_html, build_email_subject  # noqa: E402
from src.report_builder import REPORTS_DIR, load_report  # noqa: E402

load_dotenv()


def latest_report_date(base_dir: Path = REPORTS_DIR) -> str | None:
    if not base_dir.exists():
        return None
    dates = sorted(p.name for p in base_dir.iterdir() if p.is_dir())
    return dates[-1] if dates else None


def load_warnings(date: str, base_dir: Path = REPORTS_DIR) -> list[str]:
    path = base_dir / date / "warnings.json"
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def send_email(report: dict, warnings: list[str], env: dict | None = None) -> None:
    """寄出 HTML Email。env 預設讀 os.environ，測試時可傳入假的 dict 避免真的寄信。"""
    env = env if env is not None else os.environ

    smtp_host = env["SMTP_HOST"]
    smtp_port = int(env.get("SMTP_PORT", "465"))
    smtp_user = env["SMTP_USER"]
    smtp_pass = env["SMTP_PASS"]
    email_to = env["EMAIL_TO"]

    subject = build_email_subject(report)
    html = build_email_html(report, data_warnings=warnings)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = smtp_user
    msg["To"] = email_to
    msg.attach(MIMEText(html, "html", "utf-8"))

    with smtplib.SMTP_SSL(smtp_host, smtp_port) as server:
        server.login(smtp_user, smtp_pass)
        server.sendmail(smtp_user, [email_to], msg.as_string())


def main() -> int:
    date = sys.argv[1] if len(sys.argv) > 1 else latest_report_date()
    if date is None:
        print("[error] reports/ 底下沒有任何報告，請先執行 scripts/daily_pipeline.py")
        return 1

    try:
        report = load_report(date, base_dir=REPORTS_DIR)
    except FileNotFoundError:
        print(f"[error] 找不到 {date} 的報告：reports/{date}/report.json")
        return 1

    warnings = load_warnings(date)

    required_env = ["SMTP_HOST", "SMTP_USER", "SMTP_PASS", "EMAIL_TO"]
    missing = [key for key in required_env if not os.environ.get(key)]
    if missing:
        print(f"[error] 缺少環境變數：{', '.join(missing)}（請在 .env 或 Secrets 設定）")
        return 1

    send_email(report, warnings)
    print(f"Email 已寄出：{date} 的報告 -> {os.environ['EMAIL_TO']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
