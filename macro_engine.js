// ---- 巨觀經濟領先指標模型：3層分級 + 與S&P500/安聯台灣科技比對 ----
// 方法論：每個指標算自己過去60個月(5年)滾動平均/標準差的Z分數，Z>2視為「異常」。
// 17個指標依歷史回測(7次危機事件)分成3層：
//   Tier1 房市/信用結構層：平均提前CPI異常14-23個月
//   Tier2 信用/情緒/勞動層：平均提前CPI異常9-13個月
//   Tier3 即時確認層(油價/殖利率)：平均提前CPI異常1-4個月
//   Tier0 參考用(銅價、信用價差)：歷史回測命中率低，不計入分級分數，僅供參考

function monthKeyAdd(ym, n) {
  let [y, m] = ym.split("-").map(Number);
  m += n;
  y += Math.floor((m - 1) / 12);
  m = ((m - 1) % 12 + 12) % 12 + 1;
  return y + "-" + String(m).padStart(2, "0");
}
function monthDiff(a, b) {
  const [ya, ma] = a.split("-").map(Number);
  const [yb, mb] = b.split("-").map(Number);
  return (yb - ya) * 12 + (mb - ma);
}

// build a Map(month -> value) and a sorted month list for one indicator series [[month, value], ...]
function toSeriesMap(pairs) {
  const map = new Map(pairs);
  const months = pairs.map(p => p[0]);
  return { map, months };
}

// rolling z-score over a fixed window of `roll` months, requiring at least `minPeriods`.
// returns Map(month -> z) using only PAST data (no look-ahead) for each point.
function rollingZScore(pairs, roll, minPeriods, direction) {
  const z = new Map();
  const values = pairs.map(p => p[1]);
  for (let i = 0; i < pairs.length; i++) {
    const start = Math.max(0, i - roll + 1);
    const windowVals = values.slice(start, i + 1);
    if (windowVals.length < minPeriods) continue;
    const mean = windowVals.reduce((a, b) => a + b, 0) / windowVals.length;
    const variance = windowVals.reduce((a, b) => a + (b - mean) ** 2, 0) / windowVals.length;
    const std = Math.sqrt(variance);
    if (std === 0) continue;
    z.set(pairs[i][0], ((values[i] - mean) / std) * direction);
  }
  return z;
}

const ROLL = MACRO_DATA.rollWindowMonths || 60;
const MIN_PERIODS = 24;
const Z_THRESHOLD = 2;

// precompute z-score series for every indicator once.
const ZSERIES = {};
for (const key of Object.keys(MACRO_DATA.indicators)) {
  const meta = MACRO_DATA.tiers[key];
  ZSERIES[key] = rollingZScore(MACRO_DATA.indicators[key], ROLL, MIN_PERIODS, meta.direction);
}
const CPI_Z = rollingZScore(MACRO_DATA.cpi_yoy, ROLL, MIN_PERIODS, MACRO_DATA.cpiMeta.direction);

function allMonthsSorted() {
  const set = new Set();
  for (const key of Object.keys(MACRO_DATA.indicators)) for (const [m] of MACRO_DATA.indicators[key]) set.add(m);
  for (const [m] of MACRO_DATA.cpi_yoy) set.add(m);
  return Array.from(set).sort();
}
const ALL_MONTHS = allMonthsSorted();

// monthly tier-anomaly-count series across all history, for charting alongside SPY/ACDD04.
function buildTierSeries() {
  const rows = [];
  for (const m of ALL_MONTHS) {
    let t1 = 0, t1Total = 0, t2 = 0, t2Total = 0, t3 = 0, t3Total = 0;
    for (const key of Object.keys(MACRO_DATA.indicators)) {
      const meta = MACRO_DATA.tiers[key];
      if (meta.tier === 0) continue;
      const z = ZSERIES[key].get(m);
      if (z === undefined) continue;
      if (meta.tier === 1) { t1Total++; if (z > Z_THRESHOLD) t1++; }
      if (meta.tier === 2) { t2Total++; if (z > Z_THRESHOLD) t2++; }
      if (meta.tier === 3) { t3Total++; if (z > Z_THRESHOLD) t3++; }
    }
    const cpiZ = CPI_Z.get(m);
    rows.push({
      month: m, tier1: t1, tier1Total: t1Total, tier2: t2, tier2Total: t2Total, tier3: t3, tier3Total: t3Total,
      cpiAnomaly: cpiZ !== undefined && cpiZ > Z_THRESHOLD,
      compositeScore: t1 * 1 + t2 * 1.5 + t3 * 2, // later-tier signals weighted higher (closer to confirmation)
    });
  }
  return rows;
}

// current (latest available) reading for every indicator, regardless of each series' own update lag.
function currentStatus() {
  const rows = [];
  for (const key of Object.keys(MACRO_DATA.indicators)) {
    const pairs = MACRO_DATA.indicators[key];
    const meta = MACRO_DATA.tiers[key];
    const lastMonth = pairs[pairs.length - 1][0];
    const z = ZSERIES[key].get(lastMonth);
    rows.push({
      key, label: meta.label, tier: meta.tier, lastMonth,
      rawValue: pairs[pairs.length - 1][1],
      z: z === undefined ? null : z,
      anomaly: z !== undefined && z > Z_THRESHOLD,
    });
  }
  rows.sort((a, b) => (b.z || -99) - (a.z || -99));
  return rows;
}

// normalize a [[month, value], ...] series to "% change from the first point within [startMonth, endMonth]".
function normalizeSeries(pairs, startMonth, endMonth) {
  const filtered = pairs.filter(([m]) => (!startMonth || m >= startMonth) && (!endMonth || m <= endMonth));
  if (filtered.length === 0) return [];
  const base = filtered[0][1];
  return filtered.map(([m, v]) => [m, (v / base - 1) * 100]);
}

// % below the trailing all-time high, computed over the FULL series first (so the rolling
// peak isn't artificially reset at the visible window's start), then clipped to the display
// window. Crisis drawdowns stay clearly visible at any zoom level, unlike "%-from-chart-start"
// which gets compressed to near-invisibility once cumulative growth is large.
function drawdownSeries(pairs, startMonth, endMonth) {
  let peak = -Infinity;
  const full = pairs.map(([m, v]) => {
    peak = Math.max(peak, v);
    return [m, (v / peak - 1) * 100];
  });
  return full.filter(([m]) => (!startMonth || m >= startMonth) && (!endMonth || m <= endMonth));
}

// ---- valuation "regime gate": is CAPE itself, right now, in a historically expensive
// (top-10%-of-145-years) era? All 7 backtested crises happened while it was. This isn't a
// timing signal (CAPE moves slowly) - it answers "is the market structurally fragile right
// now", as a precondition for whether the faster Tier1/2/3 signals matter much if they fire.
function capeStatus() {
  const pairs = MACRO_DATA.cape;
  const values = pairs.map(p => p[1]);
  const last = pairs[pairs.length - 1];
  const sorted = [...values].sort((a, b) => a - b);
  const pctile = sorted.filter(v => v < last[1]).length / sorted.length * 100;
  const p90 = sorted[Math.floor(sorted.length * 0.9)];
  const isEstimated = MACRO_DATA.capeEstimateFrom && last[0] >= MACRO_DATA.capeEstimateFrom;
  return { month: last[0], cape: last[1], percentile: pctile, threshold90: p90, elevated: last[1] > p90, isEstimated };
}
