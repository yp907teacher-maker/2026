// 純靜態 Dashboard，沒有後端。所有資料都是相對於這個檔案往上一層抓
// （../reports_public/...），前提是 GitHub Pages 的發布來源設定為 repo 根目錄，
// 讓 dashboard/ 與 reports_public/ 是同一層的兄弟目錄。
const DATA_ROOT = "../reports_public";

const els = {
  dateSelect: document.getElementById("date-select"),
  loading: document.getElementById("loading"),
  error: document.getElementById("error"),
  content: document.getElementById("content"),
  cashPct: document.getElementById("cash-pct"),
  holdingsCount: document.getElementById("holdings-count"),
  rebalanceStatus: document.getElementById("rebalance-status"),
  holdingsTableBody: document.querySelector("#holdings-table tbody"),
  top10List: document.getElementById("top10-list"),
  predictionsList: document.getElementById("predictions-list"),
  sectorsGrid: document.getElementById("sectors-grid"),
  benchmarkToggle: document.getElementById("benchmark-toggle"),
};

let navChart = null;
let currentReport = null;

function fmtPct(value, digits = 2) {
  if (value === null || value === undefined) return "—";
  return (value * 100).toFixed(digits) + "%";
}

function pctClass(value) {
  if (value === null || value === undefined) return "";
  return value >= 0 ? "pct-pos" : "pct-neg";
}

async function fetchJson(path) {
  const resp = await fetch(path, { cache: "no-store" });
  if (!resp.ok) {
    throw new Error(`無法載入 ${path}（HTTP ${resp.status}）`);
  }
  return resp.json();
}

async function loadDateIndex() {
  const dates = await fetchJson(`${DATA_ROOT}/index.json`);
  if (!Array.isArray(dates) || dates.length === 0) {
    throw new Error("index.json 是空的，還沒有任何一天的報告資料");
  }
  return dates;
}

async function loadReport(date) {
  return fetchJson(`${DATA_ROOT}/${date}/report.json`);
}

function renderStats(report) {
  els.cashPct.textContent = fmtPct(report.cash.pct_of_total, 1);
  els.holdingsCount.textContent = report.holdings.length;

  const rb = report.rebalance;
  if (rb && rb.triggered) {
    const reasonLabel = rb.reason === "new_cash_inflow" ? "新資金匯入" : "當月首個交易日";
    els.rebalanceStatus.textContent = `已觸發（${reasonLabel}）`;
  } else {
    els.rebalanceStatus.textContent = "未觸發";
  }
}

function renderHoldings(report) {
  els.holdingsTableBody.innerHTML = "";
  const sorted = [...report.holdings].sort(
    (a, b) => (b.pct_of_portfolio ?? 0) - (a.pct_of_portfolio ?? 0)
  );

  for (const h of sorted) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${h.stock_id}</td>
      <td>${h.name}</td>
      <td>${fmtPct(h.pct_of_portfolio, 1)}</td>
      <td class="${pctClass(h.unrealized_pnl_pct)}">${fmtPct(h.unrealized_pnl_pct)}</td>
      <td class="${pctClass(h.performance["1d_pct"])}">${fmtPct(h.performance["1d_pct"])}</td>
      <td class="${pctClass(h.performance["1w_pct"])}">${fmtPct(h.performance["1w_pct"])}</td>
      <td class="${pctClass(h.performance["1m_pct"])}">${fmtPct(h.performance["1m_pct"])}</td>
      <td>${h.pe_ratio ?? "—"}</td>
    `;
    els.holdingsTableBody.appendChild(tr);
  }
}

function renderRankList(el, items, formatItem) {
  el.innerHTML = "";
  if (!items || items.length === 0) {
    el.innerHTML = "<li style='color:var(--muted)'>目前沒有資料</li>";
    return;
  }
  for (const item of items) {
    const li = document.createElement("li");
    li.innerHTML = formatItem(item);
    el.appendChild(li);
  }
}

function renderTop10(report) {
  renderRankList(
    els.top10List,
    report.top10,
    (row) => `${row.stock_id} <span class="score">score=${row.score.toFixed(4)}</span>`
  );
}

function renderPredictions(report) {
  renderRankList(
    els.predictionsList,
    report.predictions.items,
    (row) =>
      `${row.stock_id} <span class="score">predicted=${row.predicted_score.toFixed(4)}</span>` +
      `<span class="confidence">信心度 ${row.confidence}%</span>`
  );
}

function renderSectors(report) {
  els.sectorsGrid.innerHTML = "";
  for (const sector of report.watched_sectors) {
    const div = document.createElement("div");
    div.className = "sector-card";
    const changeClass = pctClass(sector.today_pct_change);
    div.innerHTML = `
      <div class="name">${sector.sector}</div>
      <div class="stocks">${sector.representative_stocks.join(", ")}</div>
      <div class="${changeClass}" style="font-size:18px;font-weight:700">
        ${fmtPct(sector.today_pct_change)}
      </div>
    `;
    els.sectorsGrid.appendChild(div);
  }
}

function renderNavChart(report) {
  const showBenchmark = els.benchmarkToggle.checked;
  const labels = report.nav_history.map((row) => row.date);
  const portfolioData = report.nav_history.map((row) => row.nav);

  const benchmarkByDate = new Map(
    (report.benchmark_nav_history || []).map((row) => [row.date, row.nav])
  );
  const benchmarkData = labels.map((date) => benchmarkByDate.get(date) ?? null);

  const datasets = [
    {
      label: "追蹤組合 NAV",
      data: portfolioData,
      borderColor: "#4f8cff",
      backgroundColor: "transparent",
      tension: 0.15,
      pointRadius: 2,
    },
  ];

  if (showBenchmark) {
    datasets.push({
      label: "大盤基準（0050）",
      data: benchmarkData,
      borderColor: "#ffb347",
      backgroundColor: "transparent",
      borderDash: [5, 4],
      tension: 0.15,
      pointRadius: 2,
    });
  }

  const ctx = document.getElementById("nav-chart").getContext("2d");
  if (navChart) {
    navChart.destroy();
  }
  navChart = new Chart(ctx, {
    type: "line",
    data: { labels, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        y: {
          ticks: { callback: (v) => v.toFixed(2) },
        },
      },
      plugins: {
        legend: { display: true },
        tooltip: {
          callbacks: {
            label: (item) => `${item.dataset.label}: ${item.formattedValue}`,
          },
        },
      },
    },
  });
}

function renderReport(report) {
  currentReport = report;
  renderStats(report);
  renderHoldings(report);
  renderTop10(report);
  renderPredictions(report);
  renderSectors(report);
  renderNavChart(report);
}

async function selectDate(date) {
  els.loading.hidden = false;
  els.content.hidden = true;
  els.error.hidden = true;
  try {
    const report = await loadReport(date);
    renderReport(report);
    els.content.hidden = false;
  } catch (err) {
    els.error.textContent = `載入 ${date} 的報告失敗：${err.message}`;
    els.error.hidden = false;
  } finally {
    els.loading.hidden = true;
  }
}

async function init() {
  try {
    const dates = await loadDateIndex();
    dates.sort().reverse(); // 最新日期在前

    els.dateSelect.innerHTML = "";
    for (const date of dates) {
      const opt = document.createElement("option");
      opt.value = date;
      opt.textContent = date;
      els.dateSelect.appendChild(opt);
    }

    els.dateSelect.addEventListener("change", (e) => selectDate(e.target.value));
    els.benchmarkToggle.addEventListener("change", () => {
      if (currentReport) renderNavChart(currentReport);
    });

    await selectDate(dates[0]);
  } catch (err) {
    els.loading.hidden = true;
    els.error.textContent = `初始化失敗：${err.message}`;
    els.error.hidden = false;
  }
}

init();
