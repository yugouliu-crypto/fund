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
function navOnOrAfter(navList, iso) {
  for (let i = 0; i < navList.length; i++) {
    if (navList[i][0] >= iso) return { idx: i, date: navList[i][0], nav: navList[i][1] };
  }
  return null;
}
function navOnOrBefore(navList, iso) {
  let res = null;
  for (let i = 0; i < navList.length; i++) {
    if (navList[i][0] <= iso) res = { idx: i, date: navList[i][0], nav: navList[i][1] };
    else break;
  }
  return res;
}
function navAt(navList, idx) {
  if (idx == null || idx >= navList.length) return null;
  return { date: navList[idx][0], nav: navList[idx][1] };
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

// ---- core rotation + redirect simulation ----
// params: { principalTWD, fx, switchDelayDays, settlementDays, redirectPct (0-1), startDate?, endDate?, order? }
// order: which funds to cycle through, in sequence (default = the 3-fund rotation).
// Pass a single-element array (e.g. ["JFZN3"]) to model "just buy and hold one fund".
function simulate(params) {
  const { FUNDS, TECH } = FUND_DATA;
  const ORDER = params.order || FUND_DATA.ORDER;
  const fx = params.fx;
  const switchDelayDays = params.switchDelayDays || 0;
  const settlementDays = params.settlementDays || 0;
  const redirectPct = params.redirectPct || 0;
  const principalTWD = params.principalTWD;
  const principalUSD = principalTWD / fx;

  const startDate = params.startDate || ORDER.map(c => FUNDS[c].nav[0][0]).reduce((a, b) => (a > b ? a : b));
  const endDate = params.endDate || ORDER.map(c => FUNDS[c].nav[FUNDS[c].nav.length - 1][0])
    .reduce((a, b) => (a < b ? a : b));

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
      if (t) techAddUnits = (redirectUSD * fx) / t.nav;
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
  const finalTechTWD = techUnits * lastTechNav.nav;

  if (missedCount > 0) {
    warnings.push(`目前設定下，模擬期間內有 ${missedCount} 次轉換來不及趕上下一支基金的配息基準日（資金尚未到位，配息已截止認列），表示這套轉換節奏在現實中可能無法完整執行。`);
  }
  if (crashGuardTriggers > 0) {
    warnings.push(`大跌暫緩轉換規則共觸發 ${crashGuardTriggers} 次（轉換日因為跌幅過大而被延後）。`);
  }

  // ---- monthly snapshot table ----
  const monthly = buildMonthly(segments, events, log, FUNDS, TECH, fx, startDate, endDate);

  return {
    startDate, endDate, cycles: log.length,
    finalPrincipalTWD, cashCumTWD, finalTechTWD,
    totalTWD: finalPrincipalTWD + finalTechTWD + cashCumTWD,
    investedOnlyTWD: finalPrincipalTWD + finalTechTWD,
    log, monthly, warnings, missedCount, crashGuardTriggers,
    techUnits, finalUnits: units, finalFund: curFund,
  };
}

function buildMonthly(segments, events, log, FUNDS, TECH, fx, startDate, endDate) {
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
    const techTWD = techNavInfo ? techUnitsCum * techNavInfo.nav : 0;

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
      totalTWD: (principalTWD || 0) + techTWD + cashCum,
      fundsHeldThisMonth: segsInMonth.map(s => FUNDS[s.fund].name),
      eventsInMonth,
    });
  }
  return rows;
}
