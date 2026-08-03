"""每日 Email 通知的 View：把 report.json 渲染成 HTML Email。

對應計劃書 Phase 5：語氣白話、專業但不艱澀，固定風險聲明，格式為 HTML Email，
版面與 Dashboard 一致的簡化視覺化（色塊/箭頭呈現漲跌，紅漲綠跌），不依賴外部
圖片服務。

Email 是寄給使用者自己的私人信箱，讀取「完整版」report（含真實金額），
跟公開版 Dashboard 讀取去敏感化資料不同，兩者是同一份 Model 的不同 View。
"""

from __future__ import annotations

RISK_DISCLAIMER = "本報告僅供資訊整理與研究參考，不構成投資建議；台股投資有風險，請自行審慎評估。"

DEFAULT_STOP_LOSS_PCT = -0.15
DEFAULT_TAKE_PROFIT_PCT = 0.30


def _fmt_money(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:,.0f}"


def _fmt_pct(value: float | None, digits: int = 2) -> str:
    if value is None:
        return "—"
    return f"{value * 100:.{digits}f}%"


def _arrow(value: float | None) -> str:
    if value is None:
        return ""
    return "▲" if value >= 0 else "▼"


def _color(value: float | None) -> str:
    """台股慣例：紅漲、綠跌，與歐美相反。"""
    if value is None:
        return "#666666"
    return "#c0304a" if value >= 0 else "#1a8a6f"


def build_email_subject(report: dict) -> str:
    return f"【台股每日分析】{report['date']} 資產總覽與前十強"


def _render_warnings(data_warnings: list[str] | None) -> str:
    if not data_warnings:
        return ""
    items = "".join(f"<li>{w}</li>" for w in data_warnings)
    return f"""
    <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:16px">
      <tr><td style="padding:12px 16px;background:#fff4e0;border:1px solid #e0a840;border-radius:8px;color:#7a4a06;font-size:13px">
        <b>⚠️ 資料不完整提醒</b>
        <ul style="margin:6px 0 0;padding-left:20px">{items}</ul>
      </td></tr>
    </table>
    """


def _render_overview(report: dict) -> str:
    cash = report["cash"]["amount"]
    total_value = report["total_value"]
    total_market_value = report["total_market_value"]
    nav_history = report.get("nav_history", [])
    latest_nav = nav_history[-1]["nav"] if nav_history else None
    prev_nav = nav_history[-2]["nav"] if len(nav_history) >= 2 else None
    day_change_pct = (
        (latest_nav - prev_nav) / prev_nav if latest_nav is not None and prev_nav else None
    )

    return f"""
    <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:20px">
      <tr><td style="padding:16px 18px;background:#f5f6fa;border-radius:10px">
        <div style="font-size:13px;color:#666">今日資產總覽</div>
        <div style="font-size:26px;font-weight:700;margin-top:4px">NT$ {_fmt_money(total_value)}</div>
        <div style="font-size:13px;color:#666;margin-top:6px">
          現金 NT$ {_fmt_money(cash)}　持股市值 NT$ {_fmt_money(total_market_value)}
        </div>
        <div style="font-size:14px;margin-top:8px;color:{_color(day_change_pct)}">
          較昨日 {_arrow(day_change_pct)} {_fmt_pct(day_change_pct)}
        </div>
      </td></tr>
    </table>
    """


def _render_holdings(report: dict) -> str:
    holdings = sorted(report["holdings"], key=lambda h: -(h["market_value"] or 0))
    if not holdings:
        return "<p style='color:#666;font-size:13px'>目前沒有持股資料。</p>"

    rows = []
    for h in holdings:
        perf = h["performance"]
        rows.append(
            f"""
            <tr>
              <td style="padding:6px 8px;border-bottom:1px solid #e5e5e5">{h['stock_id']} {h['name']}</td>
              <td style="padding:6px 8px;border-bottom:1px solid #e5e5e5;text-align:right;color:{_color(h['unrealized_pnl_pct'])}">{_fmt_pct(h['unrealized_pnl_pct'])}</td>
              <td style="padding:6px 8px;border-bottom:1px solid #e5e5e5;text-align:right;color:{_color(perf['1d_pct'])}">{_fmt_pct(perf['1d_pct'])}</td>
              <td style="padding:6px 8px;border-bottom:1px solid #e5e5e5;text-align:right;color:{_color(perf['1w_pct'])}">{_fmt_pct(perf['1w_pct'])}</td>
              <td style="padding:6px 8px;border-bottom:1px solid #e5e5e5;text-align:right;color:{_color(perf['1m_pct'])}">{_fmt_pct(perf['1m_pct'])}</td>
            </tr>
            """
        )
    return f"""
    <table width="100%" cellpadding="0" cellspacing="0" style="font-size:13px;border-collapse:collapse">
      <tr style="background:#f0f2f8">
        <th style="padding:6px 8px;text-align:left">股票</th>
        <th style="padding:6px 8px;text-align:right">損益%</th>
        <th style="padding:6px 8px;text-align:right">1日</th>
        <th style="padding:6px 8px;text-align:right">1週</th>
        <th style="padding:6px 8px;text-align:right">1月</th>
      </tr>
      {''.join(rows)}
    </table>
    """


def _render_top10(report: dict) -> str:
    items = report.get("top10", [])
    if not items:
        return "<p style='color:#666;font-size:13px'>今日尚無排名資料。</p>"
    rows = "".join(
        f"<li>{row['stock_id']}　<span style='color:#666;font-size:12px'>score={row['score']:.4f}</span></li>"
        for row in items
    )
    return f"<ol style='margin:0;padding-left:20px;font-size:13.5px'>{rows}</ol>"


def _render_predictions(report: dict) -> str:
    items = report.get("predictions", {}).get("items", [])
    if not items:
        return "<p style='color:#666;font-size:13px'>目前累積的歷史資料還不夠，暫無預測名單。</p>"
    rows = "".join(
        f"<li>{row['stock_id']}　"
        f"<span style='color:#666;font-size:12px'>predicted={row['predicted_score']:.4f}</span>　"
        f"<span style='color:#4f8cff;font-size:12px'>信心度 {row['confidence']}%</span></li>"
        for row in items
    )
    return (
        "<ol style='margin:0;padding-left:20px;font-size:13.5px'>"
        + rows
        + "</ol>"
        + "<p style='color:#999;font-size:12px;margin-top:6px'>"
        "以歷史排名分數趨勢外插估算，僅供參考，非投資建議。</p>"
    )


def _render_sectors(report: dict) -> str:
    sectors = report.get("watched_sectors", [])
    if not sectors:
        return ""
    cells = []
    for s in sectors:
        cells.append(
            f"""
            <td style="padding:10px 14px;background:#f0f2f8;border-radius:8px">
              <div style="font-weight:600;font-size:13.5px">{s['sector']}</div>
              <div style="color:#666;font-size:11.5px;margin:2px 0 6px">{', '.join(s['representative_stocks'])}</div>
              <div style="color:{_color(s['today_pct_change'])};font-weight:700">{_fmt_pct(s['today_pct_change'])}</div>
            </td>
            """
        )
    return f"""
    <table cellpadding="0" cellspacing="8"><tr>{''.join(cells)}</tr></table>
    """


def _render_signals(
    report: dict,
    stop_loss_pct: float,
    take_profit_pct: float,
) -> str:
    """重要訊號提醒：持股觸及停損/停利門檻。屬於「即時提醒」而非自動下單。"""
    alerts = []
    for h in report.get("holdings", []):
        pnl = h["unrealized_pnl_pct"]
        if pnl is None:
            continue
        if pnl <= stop_loss_pct:
            alerts.append(f"{h['stock_id']} {h['name']} 未實現損益 {_fmt_pct(pnl)}，已觸及停損提醒門檻")
        elif pnl >= take_profit_pct:
            alerts.append(f"{h['stock_id']} {h['name']} 未實現損益 {_fmt_pct(pnl)}，已觸及停利提醒門檻")

    if not alerts:
        return "<p style='color:#666;font-size:13px'>今日沒有持股觸及停損/停利提醒門檻。</p>"

    items = "".join(f"<li>{a}</li>" for a in alerts)
    return f"<ul style='margin:0;padding-left:20px;font-size:13.5px;color:#c0304a'>{items}</ul>"


def build_email_html(
    report: dict,
    data_warnings: list[str] | None = None,
    stop_loss_pct: float = DEFAULT_STOP_LOSS_PCT,
    take_profit_pct: float = DEFAULT_TAKE_PROFIT_PCT,
) -> str:
    return f"""<!DOCTYPE html>
<html lang="zh-Hant"><head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#eef0f5;font-family:-apple-system,'PingFang TC','Microsoft JhengHei',sans-serif;color:#1a1d29">
<div style="max-width:600px;margin:0 auto;padding:20px 16px">

  <h2 style="font-size:18px;margin:0 0 4px">台股每日分析 — {report['date']}</h2>
  <p style="color:#999;font-size:12px;margin:0 0 16px">產生時間：{report.get('generated_at', '—')}</p>

  {_render_warnings(data_warnings)}
  {_render_overview(report)}

  <h3 style="font-size:15px;margin:20px 0 8px">持股逐檔盈虧狀況</h3>
  {_render_holdings(report)}

  <h3 style="font-size:15px;margin:20px 0 8px">今日台股前十強</h3>
  {_render_top10(report)}

  <h3 style="font-size:15px;margin:20px 0 8px">次日預測名單</h3>
  {_render_predictions(report)}

  <h3 style="font-size:15px;margin:20px 0 8px">關注類股表現</h3>
  {_render_sectors(report)}

  <h3 style="font-size:15px;margin:20px 0 8px">重要訊號提醒</h3>
  {_render_signals(report, stop_loss_pct, take_profit_pct)}

  <p style="color:#999;font-size:11.5px;margin-top:28px;padding-top:14px;border-top:1px solid #ddd">
    {RISK_DISCLAIMER}
  </p>
</div>
</body></html>
"""
