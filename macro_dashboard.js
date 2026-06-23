let mainChart = null;
let capeChart = null;
const TIER_SERIES = buildTierSeries();
const TIER_BY_MONTH = new Map(TIER_SERIES.map(r => [r.month, r]));

function renderCapeCards() {
  const s = capeStatus();
  const cards = [
    { label: "目前CAPE(本益比，經週期調整)", value: fmtNum(s.cape, 1), sub: s.isEstimated ? `推估值(${s.month})，已用multpl.com真實數字校正過` : `官方資料(${s.month})`, cls: "" },
    { label: "145年歷史百分位", value: fmtNum(s.percentile, 0) + "%", sub: s.elevated ? "在歷史前10%最貴區間內" : "不在歷史前10%最貴區間", cls: s.elevated ? "neg" : "pos" },
    { label: "90百分位門檻值(歷史前10%最貴的分界)", value: fmtNum(s.threshold90, 1), sub: "回測過的7次危機，發生時CAPE都超過這個門檻", cls: "" },
    { label: "資產體質判定", value: s.elevated ? "偏脆弱" : "相對健康", sub: s.elevated ? "歷史上所有7次危機都在這個區間發生，後面的訊號要認真看" : "歷史上7次危機都沒有在這個區間發生過", cls: s.elevated ? "neg" : "pos" },
  ];
  document.getElementById("cape-cards").innerHTML = cards.map(c => `
    <div class="card"><div class="label">${c.label}</div><div class="value">${c.value}</div><div class="sub ${c.cls}">${c.sub}</div></div>
  `).join("");
}

function renderCapeChart() {
  const pairs = MACRO_DATA.cape;
  const s = capeStatus();
  const ctx = document.getElementById("chart-cape").getContext("2d");
  if (capeChart) capeChart.destroy();
  capeChart = new Chart(ctx, {
    type: "line",
    data: {
      labels: pairs.map(p => p[0]),
      datasets: [
        { label: "CAPE(經週期調整本益比)", data: pairs.map(p => p[1]), borderColor: "#c084fc", backgroundColor: "transparent", tension: 0.1, pointRadius: 0 },
        { label: "90百分位門檻(歷史前10%最貴)", data: pairs.map(() => s.threshold90), borderColor: "#ff6b6b", borderDash: [6, 4], pointRadius: 0, backgroundColor: "transparent" },
      ],
    },
    options: {
      responsive: true, interaction: { mode: "index", intersect: false },
      scales: {
        x: { ticks: { color: "#93a3b0", maxTicksLimit: 15 }, grid: { color: "#2e3a44" } },
        y: { ticks: { color: "#93a3b0" }, grid: { color: "#2e3a44" } },
      },
      plugins: { legend: { labels: { color: "#e8edf2" } } },
    },
  });
}

function fmtNum(n, digits = 2) { return n == null || isNaN(n) ? "-" : n.toFixed(digits); }

function rangeToStartMonth(range) {
  const lastMonth = MACRO_DATA.spy[MACRO_DATA.spy.length - 1][0];
  const spyFirstMonth = MACRO_DATA.spy[0][0];
  // "all" means "all of SPY's history" (1993+), not the risk score's own longer history
  // (back to 1947) - this chart exists to compare the score against SPY/ACDD04, so showing
  // decades of score-only data with no market line to compare against is never useful here,
  // and worse, previously let the composite-score series carry x-axis category labels the
  // SPY/ACDD04 series didn't have, which Chart.js's category scale appends out of order.
  if (range === "all") return spyFirstMonth;
  const years = range === "10y" ? 10 : 20;
  return monthKeyAdd(lastMonth, -years * 12);
}

// current tier counts use each indicator's OWN latest available reading (currentStatus()),
// not a single shared calendar month - different FRED series report on different lags, so
// forcing one shared month would understate the denominator (most series just haven't
// updated for the very latest month yet, that's not the same as "no data").
function renderTierCards() {
  const status = currentStatus();
  const byTier = { 1: { n: 0, total: 0 }, 2: { n: 0, total: 0 }, 3: { n: 0, total: 0 } };
  let latestMonth = null;
  for (const r of status) {
    if (r.tier === 0 || r.z == null) continue;
    byTier[r.tier].total++;
    if (r.anomaly) byTier[r.tier].n++;
    if (!latestMonth || r.lastMonth > latestMonth) latestMonth = r.lastMonth;
  }
  const cpiLastMonth = MACRO_DATA.cpi_yoy[MACRO_DATA.cpi_yoy.length - 1][0];
  const cpiZ = CPI_Z.get(cpiLastMonth);
  const cpiAnomaly = cpiZ !== undefined && cpiZ > Z_THRESHOLD;

  const cards = [
    { label: "Tier1 房市/信用結構層(平均提前14~23個月)", value: `${byTier[1].n}/${byTier[1].total}`, sub: byTier[1].n > 0 ? "有異常" : "目前正常", cls: byTier[1].n > 0 ? "neg" : "pos" },
    { label: "Tier2 信用/情緒/勞動層(平均提前9~13個月)", value: `${byTier[2].n}/${byTier[2].total}`, sub: byTier[2].n > 0 ? "有異常" : "目前正常", cls: byTier[2].n > 0 ? "neg" : "pos" },
    { label: "Tier3 即時確認層(平均提前1~4個月)", value: `${byTier[3].n}/${byTier[3].total}`, sub: byTier[3].n > 0 ? "有異常" : "目前正常", cls: byTier[3].n > 0 ? "neg" : "pos" },
    { label: "綜合風險分數(各指標取各自最新一筆)", value: fmtNum(byTier[1].n * 1 + byTier[2].n * 1.5 + byTier[3].n * 2, 1), sub: cpiAnomaly ? "CPI確認層也已異常" : "CPI確認層尚未異常", cls: cpiAnomaly ? "neg" : "pos" },
  ];
  document.getElementById("tier-cards").innerHTML = cards.map(c => `
    <div class="card"><div class="label">${c.label}</div><div class="value">${c.value}</div><div class="sub ${c.cls}">${c.sub}</div></div>
  `).join("");

  const warnEl = document.getElementById("warning-area");
  const totalAnomaly = byTier[1].n + byTier[2].n + byTier[3].n;
  warnEl.innerHTML = totalAnomaly === 0
    ? `<div class="warning-banner ok">✓ 目前(各指標最新資料約${latestMonth})17個指標中沒有任何一個觸發異常(Z>2)，相對平靜。</div>`
    : `<div class="warning-banner">⚠️ 目前共有 ${totalAnomaly} 個指標處於異常狀態，請參考下方明細表確認是哪幾個、屬於哪一層。</div>`;
}

function renderMainChart() {
  const range = document.querySelector('input[name="range"]:checked').value;
  const startMonth = rangeToStartMonth(range);
  const endMonth = MACRO_DATA.spy[MACRO_DATA.spy.length - 1][0];

  const datasets = [];
  if (document.getElementById("showSPY").checked) {
    const dd = drawdownSeries(MACRO_DATA.spy, startMonth, endMonth);
    datasets.push({ label: "S&P500(距歷史高點%)", data: dd.map(([m, v]) => ({ x: m, y: v })), borderColor: "#4fb3ff", backgroundColor: "transparent", tension: 0.1, pointRadius: 0, yAxisID: "y" });
  }
  if (document.getElementById("showACDD04").checked) {
    const dd = drawdownSeries(MACRO_DATA.acdd04, startMonth, endMonth);
    datasets.push({ label: "安聯台灣科技(距歷史高點%)", data: dd.map(([m, v]) => ({ x: m, y: v })), borderColor: "#ffb454", backgroundColor: "transparent", tension: 0.1, pointRadius: 0, yAxisID: "y" });
  }
  const scoreData = TIER_SERIES.filter(r => (!startMonth || r.month >= startMonth) && r.month <= endMonth)
    .map(r => ({ x: r.month, y: r.compositeScore }));
  datasets.push({ label: "綜合風險分數", data: scoreData, borderColor: "#ff6b6b", backgroundColor: "rgba(255,107,107,0.08)", fill: true, tension: 0.1, pointRadius: 0, yAxisID: "y2", borderDash: [4, 3] });

  const ctx = document.getElementById("chart-main").getContext("2d");
  if (mainChart) mainChart.destroy();
  mainChart = new Chart(ctx, {
    type: "line",
    data: { datasets },
    options: {
      responsive: true,
      interaction: { mode: "index", intersect: false },
      parsing: { xAxisKey: "x", yAxisKey: "y" },
      scales: {
        x: { type: "category", ticks: { color: "#93a3b0", maxTicksLimit: 20 }, grid: { color: "#2e3a44" } },
        y: { position: "left", max: 5, ticks: { color: "#93a3b0", callback: v => v + "%" }, grid: { color: "#2e3a44" }, title: { display: true, text: "距歷史高點%(0=創新高)", color: "#93a3b0" } },
        y2: { position: "right", ticks: { color: "#93a3b0" }, grid: { display: false }, title: { display: true, text: "綜合風險分數", color: "#93a3b0" }, min: 0 },
      },
      plugins: {
        legend: { labels: { color: "#e8edf2" } },
        tooltip: { callbacks: { label: c => `${c.dataset.label}: ${c.parsed.y.toFixed(1)}` } },
      },
    },
  });
}

function renderEventTable() {
  const tbody = document.querySelector("#event-table tbody");
  tbody.innerHTML = MACRO_DATA.events.map(ev => {
    const row = TIER_BY_MONTH.get(ev.date);
    const peakScore = row ? row.compositeScore : null;
    const windowStart = monthKeyAdd(ev.date, -24);
    let maxScore = 0;
    for (const r of TIER_SERIES) {
      if (r.month >= windowStart && r.month <= ev.date && r.compositeScore > maxScore) maxScore = r.compositeScore;
    }
    return `<tr><td style="text-align:left;">${ev.label}</td><td>${ev.date}</td><td>${fmtNum(peakScore, 1)}</td><td>${fmtNum(maxScore, 1)}</td></tr>`;
  }).join("");
}

function renderStatusTable() {
  const rows = currentStatus();
  const tbody = document.querySelector("#status-table tbody");
  const tierName = { 0: "參考", 1: "Tier1房市", 2: "Tier2信用情緒", 3: "Tier3即時" };
  tbody.innerHTML = rows.map(r => {
    const status = r.z == null ? "資料不足" : (r.anomaly ? "⚠️異常" : (r.z > 1 ? "偏高" : "正常"));
    const cls = r.anomaly ? "neg" : "";
    return `<tr class="${r.anomaly ? "miss-row" : ""}">
      <td style="text-align:left;">${r.label}</td>
      <td>${tierName[r.tier]}</td>
      <td>${r.lastMonth}</td>
      <td>${fmtNum(r.rawValue)}</td>
      <td class="${cls}">${fmtNum(r.z)}</td>
      <td class="${cls}">${status}</td>
    </tr>`;
  }).join("");
}

function render() {
  renderCapeCards();
  renderCapeChart();
  renderTierCards();
  renderMainChart();
  renderEventTable();
  renderStatusTable();
}

["showSPY", "showACDD04"].forEach(id => document.getElementById(id).addEventListener("input", render));
document.querySelectorAll('input[name="range"]').forEach(el => el.addEventListener("input", render));

render();
