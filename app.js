function fmtTWD(n) {
  if (n == null || isNaN(n)) return "-";
  return "NT$ " + Math.round(n).toLocaleString();
}
function fmtPct(n) {
  if (n == null || isNaN(n)) return "-";
  return (n >= 0 ? "+" : "") + (n * 100).toFixed(2) + "%";
}

let chart = null;
let loanRatioChart = null;
let cmpCharts = { principal: null, div: null, total: null };
const REF = 1000000; // reference principal used for per-dollar scaling (max-safe-loan search)

const STRATEGIES = [
  { key: "rotate", label: "循環轉換(三基金：摩根→安聯→聯博)", order: FUND_DATA.ORDER, color: "#4fb3ff" },
  { key: "jfzn3", label: "只放摩根多重收益", order: ["JFZN3"], color: "#ffb454" },
  { key: "albt8", label: "只放聯博美國成長", order: ["ALBT8"], color: "#3ddc97" },
  { key: "tlzn0", label: "只放安聯全球", order: ["TLZN0"], color: "#f97316" },
  { key: "two_jt", label: "兩基金循環：摩根↔安聯（拿掉聯博）", order: ["JFZN3", "TLZN0"], color: "#c084fc" },
  { key: "two_ja", label: "兩基金循環：摩根↔聯博（拿掉安聯，避開最緊的轉換腿）", order: ["JFZN3", "ALBT8"], color: "#f43f5e" },
  { key: "two_ta", label: "兩基金循環：安聯↔聯博（拿掉摩根）", order: ["TLZN0", "ALBT8"], color: "#22d3ee" },
];

// Recursive "borrow up to capPct of account value, reinvest, borrow again" cascade.
// Converges to investedTotal = principal/(1-capPct). Returns the step-by-step tranches too.
function cascadeLoan(principalTWD, capPct) {
  let accountValue = principalTWD;
  let totalLoan = 0;
  const tranches = [];
  for (let i = 0; i < 40; i++) {
    const cap = accountValue * capPct;
    const additional = cap - totalLoan;
    if (additional < 1000) break; // not worth another round
    totalLoan += additional;
    accountValue += additional;
    tranches.push({ step: i + 1, amount: additional, cumLoan: totalLoan, accountValue });
  }
  return { totalLoan, accountValue, tranches };
}

function getSelectedOrder() {
  const all = [
    { id: "fundJFZN3", code: "JFZN3" },
    { id: "fundTLZN0", code: "TLZN0" },
    { id: "fundALBT8", code: "ALBT8" },
  ];
  const order = all.filter(f => document.getElementById(f.id).checked).map(f => f.code);
  return order.length > 0 ? order : ["JFZN3"]; // never allow zero funds selected
}

function getRedirectTarget() {
  if (document.getElementById("targetVOO").checked) return "VOO";
  if (document.getElementById("targetSPY").checked) return "SPY";
  return "ACDD04";
}

function getParams() {
  const loanEnabled = document.getElementById("loanEnabled").checked;
  const loanMode = document.getElementById("loanModeCascade").checked ? "cascade" : "fixed";
  const principalTWD = parseFloat(document.getElementById("principal").value) || 1000000;
  let loanAmt = 0;
  let cascadeInfo = null;
  if (loanEnabled) {
    if (loanMode === "fixed") {
      loanAmt = parseFloat(document.getElementById("loanAmt").value) || 0;
    } else {
      const capPct = parseFloat(document.getElementById("loanCapPct").value) / 100;
      cascadeInfo = cascadeLoan(principalTWD, capPct);
      loanAmt = cascadeInfo.totalLoan;
    }
  }
  const crashGuardEnabled = document.getElementById("crashGuardEnabled").checked;
  const horizonYears = parseFloat(document.getElementById("horizon").value);
  return {
    principalTWD,
    monthlyTarget: parseFloat(document.getElementById("monthlyTarget").value) || 0,
    fx: parseFloat(document.getElementById("fx").value),
    order: getSelectedOrder(),
    horizonYears,
    redirectTarget: getRedirectTarget(),
    redirectPct: parseFloat(document.getElementById("redirect").value) / 100,
    switchDelayDays: parseInt(document.getElementById("delay").value),
    settlementDays: parseInt(document.getElementById("settle").value),
    loanEnabled, loanMode, loanAmt, cascadeInfo,
    loanRate: parseFloat(document.getElementById("loanRate").value) / 100,
    crashGuard: {
      enabled: crashGuardEnabled,
      dropPct: parseFloat(document.getElementById("crashDrop").value) / 100,
      lookbackDays: parseInt(document.getElementById("crashLookback").value),
    },
  };
}

function fundComboLabel(order) {
  return order.map(c => FUND_DATA.FUNDS[c].name).join("→");
}

function renderCards(r, principalTWD, params, ratioInfo, maxSafeLoan70, maxSafeLoan60) {
  const investedTotal = principalTWD + (params.loanAmt || 0);
  const erosion = r.investedOnlyTWD - investedTotal;
  const totalReturn = r.totalTWD / investedTotal - 1;
  const targetName = FUND_DATA.REDIRECT_TARGETS[params.redirectTarget || "ACDD04"].name;
  const comboLabel = fundComboLabel(params.order);
  const investedLabel = params.loanAmt > 0 ? `本金+${targetName} vs 投入總額(本金${fmtTWD(principalTWD)}+貸款${fmtTWD(params.loanAmt)})` : `本金+${targetName} vs 投入總額`;
  const cards = [
    { label: `期末本金市值（持有：${comboLabel}循環）`, value: fmtTWD(r.finalPrincipalTWD), sub: `目前持有：${FUND_DATA.FUNDS[r.finalFund].name}` },
    { label: "累計配息現金（未轉出部分）", value: fmtTWD(r.cashCumTWD), sub: `共完成 ${r.cycles} 次轉換／配息事件` },
    { label: `${targetName}市值`, value: fmtTWD(r.finalTechTWD), sub: r.techUnits > 0 ? `累積 ${r.techUnits.toFixed(2)} 單位` : "未轉出資金至此" },
    { label: investedLabel, value: fmtTWD(r.investedOnlyTWD), sub: fmtPct(erosion / investedTotal), subClass: erosion >= 0 ? "pos" : "neg" },
    { label: "總資產（含現金）／對投入總額報酬率", value: fmtTWD(r.totalTWD), sub: fmtPct(totalReturn), subClass: totalReturn >= 0 ? "pos" : "neg" },
  ];
  if (params.loanEnabled && params.loanAmt > 0) {
    const loanBal = loanBalanceAt(params.loanAmt, params.loanRate, r.startDate, r.endDate);
    const netWorth = r.totalTWD - loanBal;
    const netReturn = netWorth / params.principalTWD - 1;
    cards.push(
      { label: `保單貸款本息（借${fmtTWD(params.loanAmt)}，年息${(params.loanRate * 100).toFixed(2)}%）`, value: fmtTWD(loanBal), sub: `利息累積 ${fmtTWD(loanBal - params.loanAmt)}` },
      { label: "淨值（總資產－貸款本息）vs 自己出的本金", value: fmtTWD(netWorth), sub: fmtPct(netReturn), subClass: netReturn >= 0 ? "pos" : "neg" },
    );
    const breached = ratioInfo.maxRatio >= 0.7 ? "70%強制扣抵" : (ratioInfo.maxRatio >= 0.6 ? "60%通知" : "安全");
    cards.push({
      label: "貸款÷保單帳戶價值 最高比例",
      value: (ratioInfo.maxRatio * 100).toFixed(1) + "%",
      sub: ratioInfo.maxRatio >= 0.6 ? `撞到${breached}門檻(${ratioInfo.maxRatioMonth})` : `從未撞到60%門檻，最高點在${ratioInfo.maxRatioMonth || "-"}`,
      subClass: ratioInfo.maxRatio >= 0.6 ? "neg" : "pos",
    });
  }
  cards.push({
    label: "不撞70%／60%門檻的最大安全貸款（佔本金%）",
    value: fmtTWD(maxSafeLoan70) + ` (${(maxSafeLoan70 / principalTWD * 100).toFixed(1)}%)`,
    sub: `60%門檻：${fmtTWD(maxSafeLoan60)} (${(maxSafeLoan60 / principalTWD * 100).toFixed(1)}%)`,
  });
  if (params.monthlyTarget != null) {
    const numMonths = r.monthly.length;
    const avgMonthly = r.cashCumTWD / numMonths;
    const gap = avgMonthly - params.monthlyTarget;
    cards.push({
      label: `平均每月配息現金 vs 目標 ${fmtTWD(params.monthlyTarget)}/月`,
      value: fmtTWD(avgMonthly),
      sub: gap >= 0 ? `高於目標 ${fmtTWD(gap)}/月` : `低於目標 ${fmtTWD(-gap)}/月`,
      subClass: gap >= 0 ? "pos" : "neg",
    });
  }
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

function renderChart(r, principalTWD, params) {
  const labels = r.monthly.map(m => m.month);
  const principal = r.monthly.map(m => m.principalTWD);
  const tech = r.monthly.map(m => m.techTWD);
  const cash = r.monthly.map(m => m.cashCumTWD);
  const total = r.monthly.map(m => m.totalTWD);
  const ref = r.monthly.map(() => principalTWD);

  const targetName = FUND_DATA.REDIRECT_TARGETS[params.redirectTarget || "ACDD04"].name;
  const datasets = [
    { label: `本金市值（${fundComboLabel(params.order)}循環）`, data: principal, borderColor: "#4fb3ff", backgroundColor: "transparent", tension: 0.15 },
    { label: `${targetName}市值`, data: tech, borderColor: "#ffb454", backgroundColor: "transparent", tension: 0.15 },
    { label: "累積配息現金", data: cash, borderColor: "#3ddc97", backgroundColor: "transparent", tension: 0.15 },
    { label: "總資產", data: total, borderColor: "#e8edf2", backgroundColor: "transparent", borderWidth: 2.5, tension: 0.15 },
    { label: "原始本金（自己出的錢）", data: ref, borderColor: "#93a3b0", borderDash: [6, 4], pointRadius: 0, backgroundColor: "transparent" },
  ];
  if (params.loanEnabled && params.loanAmt > 0) {
    const loanBal = r.monthly.map(m => loanBalanceAt(params.loanAmt, params.loanRate, r.startDate, m.snapDate));
    const netWorth = r.monthly.map((m, i) => m.totalTWD - loanBal[i]);
    datasets.push(
      { label: "保單貸款本息", data: loanBal, borderColor: "#ff6b6b", backgroundColor: "transparent", borderDash: [3, 3], tension: 0.15 },
      { label: "淨值（總資產－貸款本息）", data: netWorth, borderColor: "#c084fc", backgroundColor: "transparent", borderWidth: 2.5, tension: 0.15 },
    );
  }

  const ctx = document.getElementById("chart").getContext("2d");
  if (chart) chart.destroy();
  chart = new Chart(ctx, {
    type: "line",
    data: { labels, datasets },
    options: {
      responsive: true,
      interaction: { mode: "index", intersect: false },
      scales: {
        x: { ticks: { color: "#93a3b0", maxTicksLimit: 24 }, grid: { color: "#2e3a44" } },
        y: { ticks: { color: "#93a3b0", callback: v => (v / 10000) + "萬" }, grid: { color: "#2e3a44" } },
      },
      plugins: {
        legend: { labels: { color: "#e8edf2" } },
        tooltip: { callbacks: { label: ctx => `${ctx.dataset.label}: ${fmtTWD(ctx.parsed.y)}` } },
      },
    },
  });
}

function renderLoanRatioChart(r, params, ratioInfo) {
  const canvas = document.getElementById("chart-loan-ratio");
  if (!params.loanEnabled || !params.loanAmt) {
    if (loanRatioChart) { loanRatioChart.destroy(); loanRatioChart = null; }
    const ctx = canvas.getContext("2d");
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    return;
  }
  const labels = ratioInfo.series.map(s => s.month);
  const ratioPct = ratioInfo.series.map(s => s.ratio * 100);
  const line60 = labels.map(() => 60);
  const line70 = labels.map(() => 70);
  const ctx = canvas.getContext("2d");
  if (loanRatioChart) loanRatioChart.destroy();
  loanRatioChart = new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [
        { label: "貸款÷保單帳戶價值", data: ratioPct, borderColor: "#4fb3ff", backgroundColor: "transparent", tension: 0.15, pointRadius: 0 },
        { label: "60%通知門檻", data: line60, borderColor: "#ffb454", borderDash: [6, 4], pointRadius: 0, backgroundColor: "transparent" },
        { label: "70%強制扣抵門檻", data: line70, borderColor: "#ff6b6b", borderDash: [6, 4], pointRadius: 0, backgroundColor: "transparent" },
      ],
    },
    options: {
      responsive: true,
      interaction: { mode: "index", intersect: false },
      scales: {
        x: { ticks: { color: "#93a3b0", maxTicksLimit: 24 }, grid: { color: "#2e3a44" } },
        y: { ticks: { color: "#93a3b0", callback: v => v + "%" }, grid: { color: "#2e3a44" } },
      },
      plugins: {
        legend: { labels: { color: "#e8edf2" } },
        tooltip: { callbacks: { label: ctx => `${ctx.dataset.label}: ${ctx.parsed.y.toFixed(1)}%` } },
      },
    },
  });
}

function renderMonthly(r, params) {
  const loanOn = params.loanEnabled && params.loanAmt > 0;
  const tbody = document.querySelector("#monthly-table tbody");
  tbody.innerHTML = r.monthly.map(m => {
    const evHtml = m.eventsInMonth.length
      ? m.eventsInMonth.map(e => `${e.fundName}除息${e.exdiv.slice(5)} 配${fmtTWD(e.divTWD)}→轉入${e.nextFundName}`).join("<br>")
      : "（本月無轉換）";
    const loanBal = loanOn ? loanBalanceAt(params.loanAmt, params.loanRate, r.startDate, m.snapDate) : 0;
    const loanCols = `<td>${fmtTWD(loanBal)}</td><td>${fmtTWD(m.totalTWD - loanBal)}</td>`;
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
      ${loanCols}
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
  const rows = pcts.map(p => ({ p, r: simulate({ ...baseParams, redirectPct: p / 100 }) }));
  tbody.innerHTML = rows.map(row => `
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
        x: { ticks: { color: "#93a3b0", maxTicksLimit: 24 }, grid: { color: "#2e3a44" } },
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

// sweep horizonYears to show how the "breakeven redirect%" and "max safe loan%" shift with
// how many years you choose to backtest - this is the "年期變化" view.
function renderHorizonTable(params) {
  const tbody = document.querySelector("#horizon-table tbody");
  const horizons = [1.9, 5, 10, 15, 20, 25, 30];
  const rows = horizons.map(h => {
    const base = { ...params, horizonYears: h, redirectPct: 0, loanAmt: 0, loanEnabled: false };
    const r0 = simulate(base);
    const erosion0 = (r0.investedOnlyTWD / params.principalTWD - 1) * 100;
    // binary search the breakeven redirect% (0~100%) using the same per-dollar trick is overkill;
    // just do a direct numeric search since redirectPct doesn't change principal scaling here.
    let lo = 0, hi = 1;
    for (let i = 0; i < 16; i++) {
      const mid = (lo + hi) / 2;
      const rr = simulate({ ...base, redirectPct: mid });
      if (rr.investedOnlyTWD < params.principalTWD) lo = mid; else hi = mid;
    }
    const breakevenPct = hi;
    const rBreak = simulate({ ...base, redirectPct: breakevenPct });
    const avgMonthly = rBreak.cashCumTWD / rBreak.monthly.length;
    const refRun = simulate({ ...base, principalTWD: REF, redirectPct: breakevenPct });
    const maxLoan70 = findMaxSafeLoan(refRun.monthly, refRun.startDate, REF, params.loanRate || 0.0399, 0.70, params.principalTWD);
    return { h, r0, erosion0, breakevenPct, avgMonthly, maxLoan70, startDate: r0.startDate };
  });
  tbody.innerHTML = rows.map(row => `
    <tr>
      <td>${row.h}年</td>
      <td>${row.startDate}</td>
      <td class="${row.erosion0 >= 0 ? "pos" : "neg"}">${row.erosion0.toFixed(1)}%</td>
      <td>${(row.breakevenPct * 100).toFixed(1)}%</td>
      <td>${fmtTWD(row.avgMonthly)}</td>
      <td>${fmtTWD(row.maxLoan70)} (${(row.maxLoan70 / params.principalTWD * 100).toFixed(1)}%)</td>
    </tr>`).join("");
}

function render() {
  const params = getParams();
  document.getElementById("v-principal").textContent = Math.round(params.principalTWD).toLocaleString();
  document.getElementById("v-monthlyTarget").textContent = Math.round(params.monthlyTarget).toLocaleString();
  document.getElementById("v-fx").textContent = params.fx.toFixed(1);
  document.getElementById("v-redirect").textContent = Math.round(params.redirectPct * 100) + "%";
  document.getElementById("v-delay").textContent = params.switchDelayDays + " 天";
  document.getElementById("v-settle").textContent = params.settlementDays + " 天";
  document.getElementById("v-loanAmt").textContent = Math.round(parseFloat(document.getElementById("loanAmt").value) || 0).toLocaleString();
  document.getElementById("v-loanRate").textContent = parseFloat(document.getElementById("loanRate").value).toFixed(2) + "%";
  document.getElementById("v-loanCapPct").textContent = document.getElementById("loanCapPct").value + "%";
  document.getElementById("v-crashDrop").textContent = document.getElementById("crashDrop").value + "%";
  document.getElementById("v-crashLookback").textContent = document.getElementById("crashLookback").value + " 天";
  document.getElementById("v-horizon").textContent = params.horizonYears <= 1.91
    ? "1.9 年（用全部真實資料）" : params.horizonYears.toFixed(1) + " 年";

  document.getElementById("loan-fields").style.display = params.loanEnabled ? "block" : "none";
  document.getElementById("loanFixedFields").style.display = params.loanMode === "fixed" ? "block" : "none";
  document.getElementById("loanCascadeFields").style.display = params.loanMode === "cascade" ? "block" : "none";
  document.getElementById("crashGuard-fields").style.display = params.crashGuard.enabled ? "block" : "none";

  if (params.cascadeInfo) {
    const c = params.cascadeInfo;
    document.getElementById("cascadeSummary").innerHTML =
      `遞迴 ${c.tranches.length} 次後收斂：累計貸款 ${fmtTWD(c.totalLoan)}，投入總額 ${fmtTWD(c.accountValue)}` +
      `（原始本金 ${fmtTWD(params.principalTWD)} 的 ${(c.accountValue / params.principalTWD).toFixed(2)} 倍）`;
  }

  // the loan amount is invested through the same rotation strategy alongside the original principal
  const investParams = { ...params, principalTWD: params.principalTWD + params.loanAmt };

  const r = simulate(investParams);
  const ratioInfo = params.loanAmt > 0 ? loanRatioSeries(r.monthly, r.startDate, params.loanAmt, params.loanRate) : { series: [], maxRatio: 0, maxRatioMonth: null };

  // reference run (no loan) to size the "max safe loan" suggestion at the user's own principal
  const refRun = simulate({ ...params, principalTWD: REF, loanAmt: 0 });
  const maxSafeLoan70 = findMaxSafeLoan(refRun.monthly, refRun.startDate, REF, params.loanRate, 0.70, params.principalTWD);
  const maxSafeLoan60 = findMaxSafeLoan(refRun.monthly, refRun.startDate, REF, params.loanRate, 0.60, params.principalTWD);
  document.getElementById("maxSafeLoanHint").textContent =
    `目前設定下，不撞70%強制扣抵門檻的最大貸款約 ${fmtTWD(maxSafeLoan70)}（本金的${(maxSafeLoan70 / params.principalTWD * 100).toFixed(1)}%）；不撞60%通知門檻約 ${fmtTWD(maxSafeLoan60)}（${(maxSafeLoan60 / params.principalTWD * 100).toFixed(1)}%）。`;

  renderWarning(r);
  renderCards(r, params.principalTWD, params, ratioInfo, maxSafeLoan70, maxSafeLoan60);
  renderChart(r, params.principalTWD, params);
  renderLoanRatioChart(r, params, ratioInfo);
  renderHorizonTable(params);
  renderMonthly(r, params);
  renderLog(r);
  renderComparison(investParams);
  renderScenarioTable(investParams);
}

// debounced trigger: long-horizon backtests can take a noticeable fraction of a second
// (the horizon-comparison table alone runs ~150 simulate() calls), so re-running on every
// single "input" tick while a slider is being dragged would feel janky. Wait for a short
// pause instead.
let renderTimer = null;
function scheduleRender() {
  if (renderTimer) clearTimeout(renderTimer);
  renderTimer = setTimeout(render, 120);
}

[
  "principal", "monthlyTarget", "fx", "horizon",
  "fundJFZN3", "fundTLZN0", "fundALBT8",
  "redirect", "delay", "settle",
  "targetACDD04", "targetVOO", "targetSPY",
  "loanEnabled", "loanAmt", "loanRate", "loanModeFixed", "loanModeCascade", "loanCapPct",
  "crashGuardEnabled", "crashDrop", "crashLookback",
].forEach(id => {
  document.getElementById(id).addEventListener("input", scheduleRender);
});

render();
