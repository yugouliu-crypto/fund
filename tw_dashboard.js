let twMainChart = null;
const TW_SCORE_SERIES = twBuildScoreSeries();
const TW_SCORE_BY_MONTH = new Map(TW_SCORE_SERIES.map(r => [r.month, r]));

function twFmtNum(n, digits = 2) { return n == null || isNaN(n) ? "-" : n.toFixed(digits); }

function twRangeToStartMonth(range) {
  const taiexFirstMonth = TW_DATA.taiex[0][0];
  if (range === "all") return taiexFirstMonth;
  const lastMonth = TW_DATA.taiex[TW_DATA.taiex.length - 1][0];
  const years = range === "10y" ? 10 : 20;
  return twMonthKeyAdd(lastMonth, -years * 12);
}

function twRenderTierCards() {
  const status = twCurrentStatus();
  let n = 0, total = 0, latestMonth = null;
  for (const r of status) {
    if (r.z == null) continue;
    total++;
    if (r.anomaly) n++;
    if (!latestMonth || r.lastMonth > latestMonth) latestMonth = r.lastMonth;
  }
  const cards = [
    { label: "異常指標數量(未加權,共6個)", value: `${n}/${total}`, sub: n > 0 ? "有異常" : "目前正常", cls: n > 0 ? "neg" : "pos" },
    { label: "綜合分數(=異常指標數量)", value: twFmtNum(n, 1), sub: "樣本小,僅供參考,不像美股版有Tier加權", cls: n > 0 ? "neg" : "pos" },
  ];
  document.getElementById("tier-cards").innerHTML = cards.map(c => `
    <div class="card"><div class="label">${c.label}</div><div class="value">${c.value}</div><div class="sub ${c.cls}">${c.sub}</div></div>
  `).join("");

  const warnEl = document.getElementById("warning-area");
  warnEl.innerHTML = n === 0
    ? `<div class="warning-banner ok">✓ 目前(各指標最新資料約${latestMonth})6個指標中沒有任何一個觸發異常(Z>2)，相對平靜。</div>`
    : `<div class="warning-banner">⚠️ 目前共有 ${n} 個指標處於異常狀態，請參考下方明細表確認是哪幾個。</div>`;
}

function twRenderMainChart() {
  const range = document.querySelector('input[name="range"]:checked').value;
  const startMonth = twRangeToStartMonth(range);
  const endMonth = TW_DATA.taiex[TW_DATA.taiex.length - 1][0];

  const datasets = [];
  if (document.getElementById("showTAIEX").checked) {
    const dd = twDrawdownSeries(TW_DATA.taiex, startMonth, endMonth);
    datasets.push({ label: "TAIEX(距歷史高點%)", data: dd.map(([m, v]) => ({ x: m, y: v })), borderColor: "#4fb3ff", backgroundColor: "transparent", tension: 0.1, pointRadius: 0, yAxisID: "y" });
  }
  if (document.getElementById("showSOX").checked) {
    const dd = twDrawdownSeries(TW_DATA.sox, startMonth, endMonth);
    datasets.push({ label: "費城半導體指數SOX(距歷史高點%)", data: dd.map(([m, v]) => ({ x: m, y: v })), borderColor: "#ffb454", backgroundColor: "transparent", tension: 0.1, pointRadius: 0, yAxisID: "y" });
  }
  const scoreData = TW_SCORE_SERIES.filter(r => (!startMonth || r.month >= startMonth) && r.month <= endMonth)
    .map(r => ({ x: r.month, y: r.compositeScore }));
  datasets.push({ label: "異常指標數量", data: scoreData, borderColor: "#ff6b6b", backgroundColor: "rgba(255,107,107,0.08)", fill: true, tension: 0.1, pointRadius: 0, yAxisID: "y2", borderDash: [4, 3] });

  const ctx = document.getElementById("chart-main").getContext("2d");
  if (twMainChart) twMainChart.destroy();
  twMainChart = new Chart(ctx, {
    type: "line",
    data: { datasets },
    options: {
      responsive: true,
      interaction: { mode: "index", intersect: false },
      parsing: { xAxisKey: "x", yAxisKey: "y" },
      scales: {
        x: { type: "category", ticks: { color: "#93a3b0", maxTicksLimit: 20 }, grid: { color: "#2e3a44" } },
        y: { position: "left", ticks: { color: "#93a3b0", callback: v => v + "%" }, grid: { color: "#2e3a44" }, title: { display: true, text: "距歷史高點%(0=創新高)", color: "#93a3b0" } },
        y2: { position: "right", ticks: { color: "#93a3b0" }, grid: { display: false }, title: { display: true, text: "異常指標數量", color: "#93a3b0" }, min: 0, max: 6 },
      },
      plugins: {
        legend: { labels: { color: "#e8edf2" } },
        tooltip: { callbacks: { label: c => `${c.dataset.label}: ${c.parsed.y.toFixed(1)}` } },
      },
    },
  });
}

function twRenderEventTable() {
  const tbody = document.querySelector("#event-table tbody");
  tbody.innerHTML = TW_DATA.events.map(ev => {
    const row = TW_SCORE_BY_MONTH.get(ev.date);
    const peakScore = row ? row.compositeScore : null;
    const windowStart = twMonthKeyAdd(ev.date, -24);
    let maxScore = 0;
    for (const r of TW_SCORE_SERIES) {
      if (r.month >= windowStart && r.month <= ev.date && r.compositeScore > maxScore) maxScore = r.compositeScore;
    }
    return `<tr><td style="text-align:left;">${ev.label}</td><td>${ev.date}</td><td>${twFmtNum(peakScore, 1)}</td><td>${twFmtNum(maxScore, 1)}</td></tr>`;
  }).join("");
}

function twRenderStatusTable() {
  const rows = twCurrentStatus();
  const tbody = document.querySelector("#status-table tbody");
  tbody.innerHTML = rows.map(r => {
    const status = r.z == null ? "資料不足" : (r.anomaly ? "⚠️異常" : (r.z > 1 ? "偏高" : "正常"));
    const cls = r.anomaly ? "neg" : "";
    return `<tr class="${r.anomaly ? "miss-row" : ""}">
      <td style="text-align:left;">${r.label}</td>
      <td>${r.lastMonth}</td>
      <td>${twFmtNum(r.rawValue)}</td>
      <td class="${cls}">${twFmtNum(r.z)}</td>
      <td class="${cls}">${status}</td>
    </tr>`;
  }).join("");
}

function twRender() {
  twRenderTierCards();
  twRenderMainChart();
  twRenderEventTable();
  twRenderStatusTable();
}

["showTAIEX", "showSOX"].forEach(id => document.getElementById(id).addEventListener("input", twRender));
document.querySelectorAll('input[name="range"]').forEach(el => el.addEventListener("input", twRender));

twRender();
