// ---- 台股版領先指標模型(早期版本) ----
// 方法論跟美股模型(macro_engine.js)完全相同：每個指標算自己過去60個月滾動平均/標準差的Z分數，Z>2視為異常。
// 跟美股版的差異：目前只有6個指標(融資餘額、出口、進口、台幣匯率、外匯存底、貿易餘額)，
// 樣本量小、回測期間也較短，還沒有像美股17指標那樣分出3層不同提前時間，所以這裡先全部視為同一層，
// 綜合分數＝異常指標數量(未加權)，不是美股版那種Tier1×1+Tier2×1.5+Tier3×2的加權分數。
// 也還沒有CAPE等價的「估值體質」層(缺台股大盤本益比歷史資料)。

function twMonthKeyAdd(ym, n) {
  let [y, m] = ym.split("-").map(Number);
  m += n;
  y += Math.floor((m - 1) / 12);
  m = ((m - 1) % 12 + 12) % 12 + 1;
  return y + "-" + String(m).padStart(2, "0");
}

function twRollingZScore(pairs, roll, minPeriods, direction) {
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

const TW_ROLL = TW_DATA.rollWindowMonths || 60;
const TW_MIN_PERIODS = 24;
const TW_Z_THRESHOLD = 2;

const TW_ZSERIES = {};
for (const key of Object.keys(TW_DATA.indicators)) {
  const meta = TW_DATA.tiers[key];
  TW_ZSERIES[key] = twRollingZScore(TW_DATA.indicators[key], TW_ROLL, TW_MIN_PERIODS, meta.direction);
}

function twAllMonthsSorted() {
  const set = new Set();
  for (const key of Object.keys(TW_DATA.indicators)) for (const [m] of TW_DATA.indicators[key]) set.add(m);
  return Array.from(set).sort();
}
const TW_ALL_MONTHS = twAllMonthsSorted();

// unweighted anomaly-count composite, since there isn't yet enough cross-indicator lead-time
// evidence (small N, short history for several series) to justify the US model's tiered weights.
function twBuildScoreSeries() {
  const rows = [];
  for (const m of TW_ALL_MONTHS) {
    let n = 0, total = 0;
    for (const key of Object.keys(TW_DATA.indicators)) {
      const z = TW_ZSERIES[key].get(m);
      if (z === undefined) continue;
      total++;
      if (z > TW_Z_THRESHOLD) n++;
    }
    rows.push({ month: m, anomalyCount: n, total, compositeScore: n });
  }
  return rows;
}

function twCurrentStatus() {
  const rows = [];
  for (const key of Object.keys(TW_DATA.indicators)) {
    const pairs = TW_DATA.indicators[key];
    const meta = TW_DATA.tiers[key];
    const lastMonth = pairs[pairs.length - 1][0];
    const z = TW_ZSERIES[key].get(lastMonth);
    rows.push({
      key, label: meta.label, lastMonth,
      rawValue: pairs[pairs.length - 1][1],
      z: z === undefined ? null : z,
      anomaly: z !== undefined && z > TW_Z_THRESHOLD,
    });
  }
  rows.sort((a, b) => (b.z || -99) - (a.z || -99));
  return rows;
}

// % below the trailing all-time high, computed over the FULL series first (same approach as
// the US model's drawdownSeries) - for TAIEX specifically this also surfaces the 1990-2020
// secular underwater period (it took 30 years to reclaim the 1990 bubble peak), which is a
// real, important fact, not a charting bug.
function twDrawdownSeries(pairs, startMonth, endMonth) {
  let peak = -Infinity;
  const full = pairs.map(([m, v]) => {
    peak = Math.max(peak, v);
    return [m, (v / peak - 1) * 100];
  });
  return full.filter(([m]) => (!startMonth || m >= startMonth) && (!endMonth || m <= endMonth));
}
