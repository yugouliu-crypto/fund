// ---- date helpers (dates are ISO strings "YYYY-MM-DD", string compare == chronological compare) ----
// All arithmetic is done in UTC to avoid local-timezone day-shift bugs when
// constructing with local time but formatting with toISOString() (UTC).
function toDateObj(iso) {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d));
}
function toISO(d) { return d.toISOString().slice(0, 10); }
function addDaysISO(iso, days) { const d = toDateObj(iso); d.setUTCDate(d.getUTCDate() + days); return toISO(d); }
function monthKey(iso) { return iso.slice(0, 7); } // YYYY-MM

// navList: array of [iso, navValue] sorted ascending. Returns {idx, date, nav} or null.
// Binary search (these get called a lot per simulate() call, and arrays can be 10k+ rows
// once long horizons are loop-extended, so a linear scan is noticeably slower).
function navOnOrAfter(navList, iso) {
  let lo = 0, hi = navList.length; // first index with navList[idx][0] >= iso
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (navList[mid][0] >= iso) hi = mid; else lo = mid + 1;
  }
  if (lo >= navList.length) return null;
  return { idx: lo, date: navList[lo][0], nav: navList[lo][1] };
}
function navOnOrBefore(navList, iso) {
  let lo = 0, hi = navList.length; // first index with navList[idx][0] > iso
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (navList[mid][0] > iso) hi = mid; else lo = mid + 1;
  }
  if (lo === 0) return null;
  const idx = lo - 1;
  return { idx, date: navList[idx][0], nav: navList[idx][1] };
}

// trailing drawdown of navList as of `iso`, looking back `lookbackDays` calendar days.
// returns a negative fraction (e.g. -0.18 = down 18%) or null if not enough history.
function trailingDrawdown(navList, iso, lookbackDays) {
  const now = navOnOrBefore(navList, iso);
  const past = navOnOrBefore(navList, addDaysISO(iso, -lookbackDays));
  if (!now || !past || past.nav === 0) return null;
  return now.nav / past.nav - 1;
}

// push targetDate forward day by day while the outgoing fund's trailing drawdown
// breaches the crash-guard threshold, so we don't lock in a switch right after a crash.
function applyCrashGuard(navList, targetDate, endDate, crashGuard) {
  if (!crashGuard || !crashGuard.enabled) return { date: targetDate, postponedDays: 0 };
  let d = targetDate;
  let postponedDays = 0;
  const maxIter = 120;
  for (let i = 0; i < maxIter; i++) {
    if (d > endDate) break;
    const dd = trailingDrawdown(navList, d, crashGuard.lookbackDays);
    if (dd == null || dd > -crashGuard.dropPct) break; // not in crash zone, ok to proceed
    d = addDaysISO(d, 1);
    postponedDays++;
  }
  return { date: d, postponedDays };
}

// ---- long-horizon support: loop-extend the 3 rotating funds' real ~23-month data ----
// JFZN3/TLZN0/ALBT8 only have real history for one ~23-month window. To backtest longer
// horizons we repeat that window (shifted forward/back in time) as many times as needed.
// IMPORTANT: loopExtendFund always reads from a pristine deep copy taken once at load time,
// never from a previously-extended result - extending an already-extended series compounds
// garbage instead of re-deriving from the real data. (We hit exactly this bug once; see
// research/README.md.)
let PRISTINE_FUNDS = null;
let CYCLE_ANCHOR_START = null;
let CYCLE_DAYS = null;

function initPristineFunds() {
  if (CYCLE_DAYS != null) return;
  PRISTINE_FUNDS = {};
  const codes = Object.keys(FUND_DATA.FUNDS);
  for (const c of codes) PRISTINE_FUNDS[c] = JSON.parse(JSON.stringify(FUND_DATA.FUNDS[c]));
  const starts = codes.map(c => PRISTINE_FUNDS[c].nav[0][0]);
  const ends = codes.map(c => PRISTINE_FUNDS[c].nav[PRISTINE_FUNDS[c].nav.length - 1][0]);
  CYCLE_ANCHOR_START = starts.reduce((a, b) => (a > b ? a : b));
  const cycleEnd = ends.reduce((a, b) => (a < b ? a : b));
  CYCLE_DAYS = Math.round((toDateObj(cycleEnd) - toDateObj(CYCLE_ANCHOR_START)) / 86400000);
}

function loopExtendFund(code, targetStart, targetEnd) {
  initPristineFunds();
  const pristine = PRISTINE_FUNDS[code];
  const newNav = [], newDiv = [];
  const baseShift = Math.round((toDateObj(targetStart) - toDateObj(CYCLE_ANCHOR_START)) / 86400000) - CYCLE_DAYS;
  const spanDays = Math.round((toDateObj(targetEnd) - toDateObj(targetStart)) / 86400000);
  const maxReps = Math.ceil(spanDays / CYCLE_DAYS) + 2;
  for (let rep = 0; rep < maxReps; rep++) {
    const shift = baseShift + rep * CYCLE_DAYS;
    for (const [d, v] of pristine.nav) {
      const nd = addDaysISO(d, shift);
      if (nd >= targetStart && nd <= targetEnd) newNav.push([nd, v]);
    }
    for (const dv of pristine.div) {
      const nb = addDaysISO(dv.basis, shift), ne = addDaysISO(dv.exdiv, shift);
      if (nb >= targetStart && nb <= targetEnd) newDiv.push({ basis: nb, exdiv: ne, amount: dv.amount });
    }
  }
  newNav.sort((a, b) => (a[0] < b[0] ? -1 : 1));
  newDiv.sort((a, b) => (a.basis < b.basis ? -1 : 1));
  return { ...pristine, nav: newNav, div: newDiv };
}

// ---- core rotation + redirect simulation ----
// params: {
//   principalTWD, fx, switchDelayDays, settlementDays, redirectPct (0-1), redirectTarget,
//   order? (default = 3-fund rotation; pass 1-3 codes to model 單配/雙配/三配),
//   startDate?, endDate?, horizonYears? (if set, endDate defaults to the latest date common
//     to all selected funds + redirect target, and startDate = endDate - horizonYears;
//     if that startDate predates the selected funds' real data, their data is loop-extended
//     from the pristine 23-month source - the redirect target itself is NEVER synthesized,
//     only clipped to its own real history if the request exceeds it),
//   crashGuard?
// }
function simulate(params) {
  initPristineFunds();
  const ORDER = params.order || FUND_DATA.ORDER;
  const TECH = FUND_DATA.REDIRECT_TARGETS[params.redirectTarget || "ACDD04"];
  const techIsUSD = TECH.currency === "USD";
  const fx = params.fx;
  const switchDelayDays = params.switchDelayDays || 0;
  const settlementDays = params.settlementDays || 0;
  const redirectPct = params.redirectPct || 0;
  const principalTWD = params.principalTWD;
  const principalUSD = principalTWD / fx;

  const realEnds = ORDER.map(c => FUND_DATA.FUNDS[c].nav[FUND_DATA.FUNDS[c].nav.length - 1][0]).concat([TECH.nav[TECH.nav.length - 1][0]]);
  const naturalEnd = realEnds.reduce((a, b) => (a < b ? a : b));
  let endDate = params.endDate || naturalEnd;

  let startDate;
  let horizonClipped = false;
  if (params.horizonYears) {
    const horizonDays = Math.round(params.horizonYears * 365.25);
    startDate = addDaysISO(endDate, -horizonDays);
  } else if (params.startDate) {
    startDate = params.startDate;
  } else {
    startDate = ORDER.map(c => FUND_DATA.FUNDS[c].nav[0][0]).reduce((a, b) => (a > b ? a : b));
  }
  // redirect target is always real data - never loop-extended. clip the window to what it actually has.
  if (startDate < TECH.nav[0][0]) { startDate = TECH.nav[0][0]; horizonClipped = true; }

  // build a local FUNDS map (never mutates FUND_DATA.FUNDS): extend any selected fund whose
  // real range doesn't cover [startDate, endDate].
  const FUNDS = {};
  for (const c of ORDER) {
    const real = FUND_DATA.FUNDS[c];
    if (startDate < real.nav[0][0] || endDate > real.nav[real.nav.length - 1][0]) {
      FUNDS[c] = loopExtendFund(c, startDate, endDate);
    } else {
      FUNDS[c] = real;
    }
  }

  let curFund = ORDER[0];
  const first = navOnOrAfter(FUNDS[curFund].nav, startDate);
  let units = principalUSD / first.nav;
  let entryDate = first.date;
  let techUnits = 0;
  let cashCumTWD = 0;

  const log = [];
  // segments for monthly mark-to-market: {fund, startDate, endDate, units}
  const segments = [];
  // cash flow events: {date, cashTWD (cumulative add), techAddUnits}
  const events = [{ date: entryDate, cashAddTWD: 0, techAddUnits: 0 }];

  const warnings = [];
  let missedCount = 0;
  let crashGuardTriggers = 0;

  while (true) {
    const fund = FUNDS[curFund];
    const nextDiv = fund.div.find(d => d.basis >= entryDate);
    if (!nextDiv || nextDiv.exdiv > endDate) break;

    const divUSD = units * nextDiv.amount;
    const redirectUSD = divUSD * redirectPct;
    const keptUSD = divUSD - redirectUSD;
    const keptTWD = keptUSD * fx;
    cashCumTWD += keptTWD;

    const requestDate = addDaysISO(nextDiv.exdiv, switchDelayDays);
    let targetDate = addDaysISO(requestDate, settlementDays);
    const guardResult = applyCrashGuard(fund.nav, targetDate, endDate, params.crashGuard);
    targetDate = guardResult.date;
    if (guardResult.postponedDays > 0) crashGuardTriggers++;

    const out = navOnOrAfter(fund.nav, targetDate);
    if (!out) break; // ran past available data
    const usdValue = units * out.nav;

    let techAddUnits = 0;
    if (redirectUSD > 0) {
      const t = navOnOrAfter(TECH.nav, targetDate);
      if (t) techAddUnits = techIsUSD ? (redirectUSD / t.nav) : ((redirectUSD * fx) / t.nav);
      techUnits += techAddUnits;
    }

    const nextFundCode = ORDER[(ORDER.indexOf(curFund) + 1) % ORDER.length];
    const nin = navOnOrAfter(FUNDS[nextFundCode].nav, targetDate);
    if (!nin) break;
    const newUnits = usdValue / nin.nav;

    // missed-dividend check: did next fund's basis date already pass before we actually landed?
    // (only meaningful when actually rotating into a different fund; "buy and hold" single-fund
    // mode has no switch to miss.)
    let missedThisLeg = false;
    if (ORDER.length > 1) {
      const nf = FUNDS[nextFundCode];
      const nfNextDiv = nf.div.find(d => d.basis >= entryDate);
      if (nfNextDiv && nfNextDiv.basis < nin.date) {
        missedThisLeg = true;
        missedCount++;
      }
    }

    segments.push({ fund: curFund, startDate: entryDate, endDate: out.date, units });
    log.push({
      fund: curFund, fundName: fund.name, entryDate, basis: nextDiv.basis, exdiv: nextDiv.exdiv,
      divPerUnit: nextDiv.amount, unitsHeld: units, divUSD, divTWD: divUSD * fx,
      keptTWD, redirectTWD: redirectUSD * fx, convertDate: out.date, navOut: out.nav,
      usdValue, nextFund: nextFundCode, nextFundName: FUNDS[nextFundCode].name,
      convertInDate: nin.date, navIn: nin.nav, newUnits, missedThisLeg,
      crashGuardPostponedDays: guardResult.postponedDays,
    });
    events.push({ date: out.date, cashAddTWD: keptTWD, techAddUnits });

    curFund = nextFundCode;
    units = newUnits;
    entryDate = nin.date;
  }

  // final mark-to-market
  const lastFundNav = navOnOrBefore(FUNDS[curFund].nav, endDate) || { date: FUNDS[curFund].nav[FUNDS[curFund].nav.length - 1][0], nav: FUNDS[curFund].nav[FUNDS[curFund].nav.length - 1][1] };
  segments.push({ fund: curFund, startDate: entryDate, endDate: lastFundNav.date, units });
  const finalPrincipalUSD = units * lastFundNav.nav;
  const finalPrincipalTWD = finalPrincipalUSD * fx;

  const lastTechNav = navOnOrBefore(TECH.nav, endDate) || { date: TECH.nav[TECH.nav.length - 1][0], nav: TECH.nav[TECH.nav.length - 1][1] };
  const finalTechTWD = techUnits * lastTechNav.nav * (techIsUSD ? fx : 1);

  if (missedCount > 0) {
    warnings.push(`目前設定下，模擬期間內有 ${missedCount} 次轉換來不及趕上下一支基金的配息基準日（資金尚未到位，配息已截止認列），表示這套轉換節奏在現實中可能無法完整執行。`);
  }
  if (crashGuardTriggers > 0) {
    warnings.push(`大跌暫緩轉換規則共觸發 ${crashGuardTriggers} 次（轉換日因為跌幅過大而被延後）。`);
  }
  if (horizonClipped) {
    warnings.push(`您要求的回測年期超過「${TECH.name}」實際歷史資料的起點，已自動把起始日縮到 ${startDate}（該標的最早可用資料）。`);
  }

  // ---- monthly snapshot table ----
  const monthly = buildMonthly(segments, events, log, FUNDS, TECH, techIsUSD, fx, startDate, endDate);

  return {
    startDate, endDate, cycles: log.length,
    finalPrincipalTWD, cashCumTWD, finalTechTWD,
    totalTWD: finalPrincipalTWD + finalTechTWD + cashCumTWD,
    investedOnlyTWD: finalPrincipalTWD + finalTechTWD,
    log, monthly, warnings, missedCount, crashGuardTriggers, horizonClipped,
    techUnits, finalUnits: units, finalFund: curFund,
  };
}

function buildMonthly(segments, events, log, FUNDS, TECH, techIsUSD, fx, startDate, endDate) {
  const months = [];
  let cursor = monthKey(startDate) + "-01";
  const endMonth = monthKey(endDate);
  while (monthKey(cursor) <= endMonth) {
    months.push(monthKey(cursor));
    const d = toDateObj(cursor);
    d.setUTCMonth(d.getUTCMonth() + 1);
    cursor = toISO(d);
  }

  const rows = [];
  for (const m of months) {
    // snapshot date = last day of this month, clipped to endDate
    const d = toDateObj(m + "-01");
    d.setUTCMonth(d.getUTCMonth() + 1);
    d.setUTCDate(d.getUTCDate() - 1);
    let snap = toISO(d);
    if (snap > endDate) snap = endDate;

    const seg = segments.find(s => snap >= s.startDate && snap <= s.endDate) || segments[segments.length - 1];
    const navInfo = navOnOrBefore(FUNDS[seg.fund].nav, snap);
    const principalTWD = navInfo ? seg.units * navInfo.nav * fx : null;

    let cashCum = 0, techUnitsCum = 0, divThisMonthTWD = 0;
    for (const e of events) {
      if (e.date <= snap) {
        cashCum += e.cashAddTWD;
        techUnitsCum += e.techAddUnits;
      }
      if (monthKey(e.date) === m) divThisMonthTWD += e.cashAddTWD;
    }
    const techNavInfo = navOnOrBefore(TECH.nav, snap);
    const techTWD = techNavInfo ? techUnitsCum * techNavInfo.nav * (techIsUSD ? fx : 1) : 0;

    // which fund(s) were actually held at some point during this calendar month
    // (a single calendar month often contains a full rotation through 2-3 funds,
    // since one full JFZN3->TLZN0->ALBT8 loop takes about a month but isn't
    // aligned to calendar boundaries)
    const segsInMonth = segments.filter(s => monthKey(s.startDate) <= m && monthKey(s.endDate) >= m);
    const eventsInMonth = log.filter(l => monthKey(l.exdiv) === m).map(l => ({
      fund: l.fund, fundName: l.fundName, exdiv: l.exdiv, divTWD: l.divTWD, keptTWD: l.keptTWD,
      redirectTWD: l.redirectTWD, nextFundName: l.nextFundName,
    }));

    rows.push({
      month: m, fund: seg.fund, fundName: FUNDS[seg.fund].name, snapDate: snap,
      units: seg.units, navUsed: navInfo ? navInfo.nav : null,
      principalTWD, divThisMonthTWD, cashCumTWD: cashCum, techTWD,
      accountValueTWD: (principalTWD || 0) + techTWD,
      totalTWD: (principalTWD || 0) + techTWD + cashCum,
      fundsHeldThisMonth: segsInMonth.map(s => FUNDS[s.fund].name),
      eventsInMonth,
    });
  }
  return rows;
}

// ---- policy loan helpers ----
// simple interest: balance(t) = principal * (1 + rate * daysElapsed/365)
function loanBalanceAt(loanAmt, loanRate, startDateISO, asOfISO) {
  if (!loanAmt) return 0;
  const days = (toDateObj(asOfISO) - toDateObj(startDateISO)) / 86400000;
  return loanAmt * (1 + (loanRate * Math.max(days, 0)) / 365);
}

// "保單帳戶價值" = 循環本金市值 + 轉出標的市值 (m.accountValueTWD already is this, per month).
// Returns the month-by-month loan/accountValue ratio plus the worst point reached.
function loanRatioSeries(monthly, startDate, loanAmt, loanRate) {
  let maxRatio = 0, maxRatioMonth = null;
  let firstBreach50 = null, firstBreach60 = null, firstBreach70 = null;
  const series = monthly.map(m => {
    const loanBal = loanBalanceAt(loanAmt, loanRate, startDate, m.snapDate);
    const ratio = m.accountValueTWD > 0 ? loanBal / m.accountValueTWD : Infinity;
    if (ratio > maxRatio) { maxRatio = ratio; maxRatioMonth = m.month; }
    if (ratio >= 0.5 && !firstBreach50) firstBreach50 = m.month;
    if (ratio >= 0.6 && !firstBreach60) firstBreach60 = m.month;
    if (ratio >= 0.7 && !firstBreach70) firstBreach70 = m.month;
    return { month: m.month, loanBal, accountValueTWD: m.accountValueTWD, ratio };
  });
  return { series, maxRatio, maxRatioMonth, firstBreach50, firstBreach60, firstBreach70 };
}

// binary search: largest loan amount (for a borrower contributing `principal`) such that the
// loan/accountValue ratio never exceeds `threshold` across the whole monthly series.
// `monthlyAtRef` must come from a simulate() call whose principalTWD == `ref` (any convenient
// reference size, e.g. 1,000,000) - since everything scales linearly with invested principal,
// we derive a per-dollar factor k(t) = accountValue(t)/ref, then accountValue for an actual
// (principal+loan) invested amount = (principal+loan)*k(t). This avoids re-running simulate()
// inside the search loop.
function findMaxSafeLoan(monthlyAtRef, startDate, ref, loanRate, threshold, principal) {
  function maxRatioForLoan(loan) {
    const invested = principal + loan;
    let maxRatio = 0;
    for (const m of monthlyAtRef) {
      const loanBal = loanBalanceAt(loan, loanRate, startDate, m.snapDate);
      const k = m.accountValueTWD / ref;
      const ratio = loanBal / (invested * k);
      if (ratio > maxRatio) maxRatio = ratio;
    }
    return maxRatio;
  }
  let lo = 0, hi = principal * 20;
  for (let i = 0; i < 60; i++) {
    const mid = (lo + hi) / 2;
    if (maxRatioForLoan(mid) > threshold) hi = mid; else lo = mid;
  }
  return lo;
}
