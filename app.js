function fmtTWD(n) {
  if (n == null || isNaN(n)) return "-";
  return "NT$ " + Math.round(n).toLocaleString();
}
function fmtPct(n) {
  return (n >= 0 ? "+" : "") + (n * 100).toFixed(2) + "%";
}

let chart = null;
let cmpCharts = { principal: null, div: null, total: null };

const STRATEGIES = [
  { key: "rotate", label: "循環轉換(三基金)", order: FUND_DATA.ORDER, color: "#4fb3ff" },
  { key: "jfzn3", label: "只放摩根多重收益", order: ["JFZN3"], color: "#ffb454" },
  { key: "albt8", label: "只放聯博美國成長", order: ["ALBT8"], color: "#3ddc97" },
];

function getParams() {
  return {
    principalTWD: parseFloat(document.getElementById("principal").value) || 1000000,
    fx: parseFloat(document.getElementById("fx").value),
    redirectPct: parseFloat(document.getElementById("redirect").value) / 100,
    switchDelayDays: parseInt(document.getElementById("delay").value),
    settlementDays: parseInt(document.getElementById("settle").value),
  };
}

function renderCards(r, principalTWD) {
  const erosion = r.investedOnlyTWD - principalTWD;
  const totalReturn = r.totalTWD / principalTWD - 1;
  const cards = [
    { label: "期末本金市值（仍在三基金循環中）", value: fmtTWD(r.finalPrincipalTWD), sub: `持有：${FUND_DATA.FUNDS[r.finalFund].name}` },
    { label: "累計配息現金（未轉出部分）", value: fmtTWD(r.cashCumTWD), sub: `共完成 ${r.cycles} 次轉換` },
    { label: "安聯台灣科技基金市值", value: fmtTWD(r.finalTechTWD), sub: r.techUnits > 0 ? `累積 ${r.techUnits.toFixed(2)} 單位` : "未轉出資金至此" },
    { label: "本金+科技基金 vs 原始本金", value: fmtTWD(r.investedOnlyTWD), sub: fmtPct(erosion / principalTWD), subClass: erosion >= 0 ? "pos" : "neg" },
    { label: "總資產（含現金）／總報酬率", value: fmtTWD(r.totalTWD), sub: fmtPct(totalReturn), subClass: totalReturn >= 0 ? "pos" : "neg" },
  ];
  document.getElementById("cards").innerHTML = cards.map(c => `
    <div class="card">
      <div class="label">${c.label}</div>
      <div class="value">${c.value}</div>
      <div class="sub ${c.subClass || ""}">${c.sub}</div>
    </div>`).join("");
}

function renderWarning(r) {
  const el = document.getElementById("warning-area");
  if (r.warnings.length > 0) {
    el.innerHTML = `<div class="warning-banner">⚠️ ${r.warnings.join("<br>")}</div>`;
  } else {
    el.innerHTML = `<div class="warning-banner ok">✓ 目前設定下，模擬期間內每一次轉換都能在下一支基金的配息基準日前到位，沒有漏接配息。</div>`;
  }
}

function renderChart(r, principalTWD) {
  const labels = r.monthly.map(m => m.month);
  const principal = r.monthly.map(m => m.principalTWD);
  const tech = r.monthly.map(m => m.techTWD);
  const cash = r.monthly.map(m => m.cashCumTWD);
  const total = r.monthly.map(m => m.totalTWD);
  const ref = r.monthly.map(() => principalTWD);

  const ctx = document.getElementById("chart").getContext("2d");
  if (chart) chart.destroy();
  chart = new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [
        { label: "本金市值（三基金循環）", data: principal, borderColor: "#4fb3ff", backgroundColor: "transparent", tension: 0.15 },
        { label: "安聯台灣科技基金市值", data: tech, borderColor: "#ffb454", backgroundColor: "transparent", tension: 0.15 },
        { label: "累積配息現金", data: cash, borderColor: "#3ddc97", backgroundColor: "transparent", tension: 0.15 },
        { label: "總資產", data: total, borderColor: "#e8edf2", backgroundColor: "transparent", borderWidth: 2.5, tension: 0.15 },
        { label: "原始本金", data: ref, borderColor: "#93a3b0", borderDash: [6, 4], pointRadius: 0, backgroundColor: "transparent" },
      ],
    },
    options: {
      responsive: true,
      interaction: { mode: "index", intersect: false },
      scales: {
        x: { ticks: { color: "#93a3b0" }, grid: { color: "#2e3a44" } },
        y: { ticks: { color: "#93a3b0", callback: v => (v / 10000) + "萬" }, grid: { color: "#2e3a44" } },
      },
      plugins: {
        legend: { labels: { color: "#e8edf2" } },
        tooltip: { callbacks: { label: ctx => `${ctx.dataset.label}: ${fmtTWD(ctx.parsed.y)}` } },
      },
    },
  });
}

function renderMonthly(r) {
  const tbody = document.querySelector("#monthly-table tbody");
  tbody.innerHTML = r.monthly.map(m => {
    const evHtml = m.eventsInMonth.length
      ? m.eventsInMonth.map(e => `${e.fundName}除息${e.exdiv.slice(5)} 配${fmtTWD(e.divTWD)}→轉入${e.nextFundName}`).join("<br>")
      : "（本月無轉換）";
    return `
    <tr>
      <td>${m.month}</td>
      <td style="text-align:left;font-size:11.5px;line-height:1.6;">${evHtml}</td>
      <td>${m.fundName}（${m.units.toFixed(0)}單位）</td>
      <td>${fmtTWD(m.principalTWD)}</td>
      <td>${m.divThisMonthTWD ? fmtTWD(m.divThisMonthTWD) : "-"}</td>
      <td>${fmtTWD(m.cashCumTWD)}</td>
      <td>${fmtTWD(m.techTWD)}</td>
      <td>${fmtTWD(m.totalTWD)}</td>
    </tr>`;
  }).join("");
}

function renderLog(r) {
  const tbody = document.querySelector("#log-table tbody");
  tbody.innerHTML = r.log.map((l, i) => `
    <tr class="${l.missedThisLeg ? "miss-row" : ""}">
      <td>${i + 1}</td>
      <td>${l.fundName}</td>
      <td>${l.basis}</td>
      <td>${l.exdiv}</td>
      <td>${l.divPerUnit}</td>
      <td>${l.unitsHeld.toFixed(2)}</td>
      <td>${fmtTWD(l.divTWD)}</td>
      <td>${l.navOut.toFixed(4)}</td>
      <td>${l.nextFundName}</td>
      <td>${l.navIn.toFixed(4)}</td>
      <td>${l.newUnits.toFixed(2)}</td>
      <td>${l.convertInDate}${l.missedThisLeg ? " ⚠️來不及" : ""}</td>
    </tr>`).join("");
}

function renderScenarioTable(baseParams) {
  const tbody = document.querySelector("#scenario-table tbody");
  const pcts = [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100];
  let bestIdx = -1, bestVal = -Infinity;
  const rows = pcts.map(p => {
    const r = simulate({ ...baseParams, redirectPct: p / 100 });
    return { p, r };
  });
  rows.forEach((row, i) => { if (row.r.investedOnlyTWD > bestVal) { bestVal = row.r.investedOnlyTWD; bestIdx = i; } });
  tbody.innerHTML = rows.map((row, i) => `
    <tr>
      <td>${row.p}%</td>
      <td>${fmtTWD(row.r.finalPrincipalTWD)}</td>
      <td>${fmtTWD(row.r.finalTechTWD)}</td>
      <td class="${row.r.investedOnlyTWD >= baseParams.principalTWD ? "best" : ""}">${fmtTWD(row.r.investedOnlyTWD)}</td>
      <td>${fmtTWD(row.r.cashCumTWD)}</td>
      <td>${fmtTWD(row.r.totalTWD)}</td>
    </tr>`).join("");
}

function computeComparison(baseParams) {
  // force every strategy onto the same start/end window so they're directly comparable
  const rotateBounds = simulate({ ...baseParams, order: FUND_DATA.ORDER });
  const startDate = rotateBounds.startDate;
  const endDate = rotateBounds.endDate;
  return STRATEGIES.map(s => ({
    ...s,
    result: simulate({ ...baseParams, order: s.order, startDate, endDate }),
  }));
}

function renderCompareTable(strategies, principalTWD) {
  const tbody = document.querySelector("#compare-table tbody");
  tbody.innerHTML = strategies.map(s => {
    const r = s.result;
    const totalReturn = r.totalTWD / principalTWD - 1;
    return `<tr>
      <td style="text-align:left;">${s.label}</td>
      <td>${fmtTWD(r.finalPrincipalTWD)}</td>
      <td>${fmtTWD(r.cashCumTWD)}</td>
      <td>${fmtTWD(r.finalTechTWD)}</td>
      <td>${fmtTWD(r.investedOnlyTWD)}</td>
      <td>${fmtTWD(r.totalTWD)}</td>
      <td class="${totalReturn >= 0 ? "pos" : "neg"}">${fmtPct(totalReturn)}</td>
    </tr>`;
  }).join("");
}

function lineDataset(s, field) {
  return {
    label: s.label,
    data: s.result.monthly.map(m => m[field]),
    borderColor: s.color,
    backgroundColor: "transparent",
    tension: 0.15,
  };
}

function renderCompareChart(canvasId, key, field, strategies) {
  const labels = strategies[0].result.monthly.map(m => m.month);
  const ctx = document.getElementById(canvasId).getContext("2d");
  if (cmpCharts[key]) cmpCharts[key].destroy();
  cmpCharts[key] = new Chart(ctx, {
    type: "line",
    data: { labels, datasets: strategies.map(s => lineDataset(s, field)) },
    options: {
      responsive: true,
      interaction: { mode: "index", intersect: false },
      scales: {
        x: { ticks: { color: "#93a3b0" }, grid: { color: "#2e3a44" } },
        y: { ticks: { color: "#93a3b0", callback: v => (v / 10000) + "萬" }, grid: { color: "#2e3a44" } },
      },
      plugins: {
        legend: { labels: { color: "#e8edf2" } },
        tooltip: { callbacks: { label: ctx => `${ctx.dataset.label}: ${fmtTWD(ctx.parsed.y)}` } },
      },
    },
  });
}

function renderComparison(baseParams) {
  const strategies = computeComparison(baseParams);
  renderCompareTable(strategies, baseParams.principalTWD);
  renderCompareChart("chart-cmp-principal", "principal", "principalTWD", strategies);
  renderCompareChart("chart-cmp-div", "div", "cashCumTWD", strategies);
  renderCompareChart("chart-cmp-total", "total", "totalTWD", strategies);
}

function render() {
  const params = getParams();
  document.getElementById("v-principal").textContent = Math.round(params.principalTWD).toLocaleString();
  document.getElementById("v-fx").textContent = params.fx.toFixed(1);
  document.getElementById("v-redirect").textContent = Math.round(params.redirectPct * 100) + "%";
  document.getElementById("v-delay").textContent = params.switchDelayDays + " 天";
  document.getElementById("v-settle").textContent = params.settlementDays + " 天";

  const r = simulate(params);
  renderWarning(r);
  renderCards(r, params.principalTWD);
  renderChart(r, params.principalTWD);
  renderMonthly(r);
  renderLog(r);
  renderComparison(params);
  renderScenarioTable(params);
}

["principal", "fx", "redirect", "delay", "settle"].forEach(id => {
  document.getElementById(id).addEventListener("input", render);
});

render();
