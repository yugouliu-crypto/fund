// ---- 分支式保單貸款裂變模擬 ----
// 規則：保單A投入(本金+貸款)，每月配息一部分留現金、一部分轉出買安聯台灣科技。
// 每當某張保單自己的安聯科技市值，再累積滿一個「貸款額度」(=第一張保單的本金×貸款成數)，
// 就可以再借出同額度去開一張新保單(新保單本金=借來的這筆錢，本身先不疊加貸款)。
// 因為這個額度全體加總可能短時間內被跨過很多次(尤其後期安聯科技噴發期)，
// 不現實——所以加一個限制：全體每年最多開一張新保單，多出來的需求往後排隊。
const ORDER = ["ALBT8"];
const TARGET = "ACDD04";
const FX = 31.5;

let chartIncome = null, chartTotal = null;

function runPolicySeries(principalTWD, startDate, redirectPct, stepAmt) {
  const r = simulate({ principalTWD, fx: FX, order: ORDER, redirectPct, redirectTarget: TARGET, startDate });
  const crossings = [];
  let nextMultiple = stepAmt;
  for (const m of r.monthly) {
    while (m.techTWD >= nextMultiple) { crossings.push(m.snapDate); nextMultiple += stepAmt; }
  }
  return { crossings, monthly: r.monthly, startDate: r.startDate, endDate: r.endDate, horizonClipped: r.horizonClipped };
}

function buildCascade(principal, loanRatio, redirectPct) {
  const loanAmt = Math.round(principal * loanRatio);
  // start as early as possible: ALBT8 only has ~23 real months so this loop-extends backwards;
  // ACDD04 (the redirect target) is never loop-extended and will auto-clip to its own real start (~2001-04).
  const startDate0 = "2001-01-01";
  // policy A invests own principal + its own initial loan together, like the rest of the site's model
  const policies = []; // {id, parent, openedDate, principal, result}
  const resA = runPolicySeries(principal + loanAmt, startDate0, redirectPct, loanAmt);
  policies.push({ id: "A", parent: null, openedDate: resA.startDate, principal: principal + loanAmt, result: resA });

  let pending = resA.crossings.map(d => ({ readyDate: d, sourceId: "A" }));
  const yearUsed = {};
  let nextId = 1;
  const endCap = resA.endDate; // natural end of available data
  let guard = 0;
  while (pending.length > 0 && guard < 300) {
    guard++;
    pending.sort((a, b) => (a.readyDate < b.readyDate ? -1 : 1));
    const ev = pending.shift();
    let openYear = ev.readyDate.slice(0, 4);
    while (yearUsed[openYear]) openYear = String(Number(openYear) + 1);
    const openDate = openYear === ev.readyDate.slice(0, 4) ? ev.readyDate : openYear + "-01-01";
    if (openDate >= endCap) continue;
    yearUsed[openYear] = true;
    const childId = "P" + nextId++;
    const res = runPolicySeries(loanAmt, openDate, redirectPct, loanAmt);
    policies.push({ id: childId, parent: ev.sourceId, openedDate: openDate, principal: loanAmt, result: res });
    for (const d of res.crossings) pending.push({ readyDate: d, sourceId: childId });
  }
  return { policies, loanAmt, endCap };
}

function trailing12Avg(monthly, idx) {
  const start = Math.max(0, idx - 11);
  let sum = 0;
  for (let i = start; i <= idx; i++) sum += monthly[i].divThisMonthTWD || 0;
  return sum / (idx - start + 1);
}

function combinedSeries(cascade) {
  // union of all months across all policies, from the earliest start to the overall end
  const allMonths = new Set();
  for (const p of cascade.policies) for (const m of p.result.monthly) allMonths.add(m.month);
  const months = Array.from(allMonths).sort();
  const rows = months.map(month => {
    let income = 0, total = 0, activeCount = 0;
    for (const p of cascade.policies) {
      const idx = p.result.monthly.findIndex(m => m.month === month);
      if (idx >= 0) {
        income += trailing12Avg(p.result.monthly, idx);
        const m = p.result.monthly[idx];
        total += (m.principalTWD || 0) + m.techTWD + m.cashCumTWD;
        activeCount++;
      }
    }
    return { month, income, total, activeCount };
  });
  return rows;
}

function stateAt(policy, atMonth) {
  // last row with month <= atMonth
  let best = null;
  for (const m of policy.result.monthly) {
    if (m.month <= atMonth) best = m; else break;
  }
  return best;
}

function harvestAt(cascade, harvestMonth) {
  const active = cascade.policies.filter(p => p.openedDate.slice(0, 7) <= harvestMonth);
  let mergedPrincipal = 0, mergedTech = 0, mergedCash = 0;
  const rows = [];
  for (const p of active) {
    const st = stateAt(p, harvestMonth);
    if (!st) continue;
    mergedPrincipal += st.principalTWD || 0;
    mergedTech += st.techTWD;
    mergedCash += st.cashCumTWD;
    rows.push({ id: p.id, principalTWD: st.principalTWD, techTWD: st.techTWD, cashCumTWD: st.cashCumTWD });
  }
  const mergedTotal = mergedPrincipal + mergedTech;
  let monthlyIncome = 0;
  if (mergedTotal > 0) {
    // force a 1-year forward window from the harvest date (ALBT8 loop-extends automatically if
    // this falls past its real data) so there's always enough room to observe ~12 dividend
    // events, regardless of how close the harvest date is to the end of the available data.
    const harvestStart = harvestMonth + "-01";
    const forwardEnd = addDaysISO(harvestStart, 365);
    const r = simulate({ principalTWD: mergedTotal, fx: FX, order: ORDER, redirectPct: 0, redirectTarget: TARGET, startDate: harvestStart, endDate: forwardEnd });
    monthlyIncome = r.monthly.length ? trailing12Avg(r.monthly, r.monthly.length - 1) : 0;
  }
  return { active: rows, mergedPrincipal, mergedTech, mergedCash, mergedTotal, monthlyIncome, policyCount: active.length };
}

function fmtTWD(n) { if (n == null || isNaN(n)) return "-"; return "NT$ " + Math.round(n).toLocaleString(); }

function getParams() {
  return {
    principal: parseFloat(document.getElementById("principal").value) || 2000000,
    loanRatio: parseFloat(document.getElementById("loanRatio").value) / 100,
    redirectPct: 1 - parseFloat(document.getElementById("withdrawPct").value) / 100,
    harvestMonth: document.getElementById("harvestDate").value,
  };
}

function renderPolicyTable(cascade) {
  const tbody = document.querySelector("#policy-table tbody");
  tbody.innerHTML = cascade.policies.map(p => {
    const last = p.result.monthly[p.result.monthly.length - 1];
    return `<tr>
      <td>${p.id}</td>
      <td>${p.parent || "（本尊）"}</td>
      <td>${p.openedDate}</td>
      <td>${fmtTWD(p.principal)}</td>
      <td>本金${fmtTWD(last.principalTWD)}＋安聯科技${fmtTWD(last.techTWD)}＋現金${fmtTWD(last.cashCumTWD)}</td>
    </tr>`;
  }).join("");
}

function renderCharts(rows) {
  const labels = rows.map(r => r.month);
  const income = rows.map(r => r.income);
  const total = rows.map(r => r.total);

  const ctx1 = document.getElementById("chart-income").getContext("2d");
  if (chartIncome) chartIncome.destroy();
  chartIncome = new Chart(ctx1, {
    type: "line",
    data: { labels, datasets: [{ label: "全體合計月配息現金(近12月平均)", data: income, borderColor: "#3ddc97", backgroundColor: "transparent", tension: 0.15, pointRadius: 0 }] },
    options: {
      responsive: true, interaction: { mode: "index", intersect: false },
      scales: { x: { ticks: { color: "#93a3b0", maxTicksLimit: 20 }, grid: { color: "#2e3a44" } }, y: { ticks: { color: "#93a3b0", callback: v => (v / 10000) + "萬" }, grid: { color: "#2e3a44" } } },
      plugins: { legend: { labels: { color: "#e8edf2" } }, tooltip: { callbacks: { label: c => `${c.dataset.label}: ${fmtTWD(c.parsed.y)}` } } },
    },
  });

  const ctx2 = document.getElementById("chart-total").getContext("2d");
  if (chartTotal) chartTotal.destroy();
  chartTotal = new Chart(ctx2, {
    type: "line",
    data: { labels, datasets: [{ label: "全體合計總資產", data: total, borderColor: "#4fb3ff", backgroundColor: "transparent", tension: 0.15, pointRadius: 0 }] },
    options: {
      responsive: true, interaction: { mode: "index", intersect: false },
      scales: { x: { ticks: { color: "#93a3b0", maxTicksLimit: 20 }, grid: { color: "#2e3a44" } }, y: { ticks: { color: "#93a3b0", callback: v => (v / 10000) + "萬" }, grid: { color: "#2e3a44" } } },
      plugins: { legend: { labels: { color: "#e8edf2" } }, tooltip: { callbacks: { label: c => `${c.dataset.label}: ${fmtTWD(c.parsed.y)}` } } },
    },
  });
}

function renderCards(cascade, rows) {
  const last = rows[rows.length - 1];
  const loanAmt = cascade.loanAmt;
  document.getElementById("cards").innerHTML = [
    { label: "每次再借/開新保單的固定額度", value: fmtTWD(loanAmt), sub: "= 本金 × 貸款成數" },
    { label: "目前(資料結尾)已開出保單數", value: cascade.policies.length + " 張", sub: "本尊1張＋子保單" + (cascade.policies.length - 1) + "張" },
    { label: "全體合計月配息現金(近12月平均)", value: fmtTWD(last.income), sub: "資料結尾 " + last.month },
    { label: "全體合計總資產", value: fmtTWD(last.total), sub: "本金市值＋安聯科技市值＋累積配息現金" },
  ].map(c => `<div class="card"><div class="label">${c.label}</div><div class="value">${c.value}</div><div class="sub">${c.sub}</div></div>`).join("");
}

function renderHarvest(h, harvestMonth) {
  document.getElementById("harvest-cards").innerHTML = [
    { label: `收割時間點 ${harvestMonth} 已存在的保單數`, value: h.policyCount + " 張", sub: "" },
    { label: "收割時合計本金+安聯科技市值", value: fmtTWD(h.mergedTotal), sub: "另外還有現金 " + fmtTWD(h.mergedCash) + "(不影響被動收入估算)" },
    { label: "全部轉回配息基金後估算月被動收入", value: fmtTWD(h.monthlyIncome), sub: "假設轉換後不再轉出，全部配息留存現金" },
  ].map(c => `<div class="card"><div class="label">${c.label}</div><div class="value">${c.value}</div><div class="sub">${c.sub}</div></div>`).join("");
}

function render() {
  const params = getParams();
  document.getElementById("v-principal").textContent = Math.round(params.principal).toLocaleString();
  document.getElementById("v-loanRatio").textContent = Math.round(params.loanRatio * 100) + "%";
  document.getElementById("v-withdrawPct").textContent = Math.round((1 - params.redirectPct) * 100) + "%";

  const cascade = buildCascade(params.principal, params.loanRatio, params.redirectPct);
  const rows = combinedSeries(cascade);

  const warnEl = document.getElementById("warning-area");
  const clippedAny = cascade.policies.some(p => p.result.horizonClipped);
  warnEl.innerHTML = clippedAny
    ? `<div class="warning-banner">⚠️ 部分保單的起算日已經超過安聯台灣科技實際資料起點，已自動截斷。</div>`
    : `<div class="warning-banner ok">✓ 全部保單都在資料涵蓋範圍內。每年最多開一張新保單的限制下，目前共開出 ${cascade.policies.length} 張保單。</div>`;

  renderCards(cascade, rows);
  renderCharts(rows);
  renderPolicyTable(cascade);

  let harvestMonth = params.harvestMonth;
  if (harvestMonth > cascade.endCap.slice(0, 7)) harvestMonth = cascade.endCap.slice(0, 7);
  const h = harvestAt(cascade, harvestMonth);
  renderHarvest(h, harvestMonth);
}

let renderTimer = null;
function scheduleRender() {
  if (renderTimer) clearTimeout(renderTimer);
  renderTimer = setTimeout(render, 150);
}

["principal", "loanRatio", "withdrawPct", "harvestDate"].forEach(id => {
  document.getElementById(id).addEventListener("input", scheduleRender);
});

render();
