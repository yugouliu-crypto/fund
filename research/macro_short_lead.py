import pandas as pd
import numpy as np
import os

BASE = os.path.dirname(os.path.abspath(__file__))
df = pd.read_csv(os.path.join(BASE, "macro_final.csv"), index_col=0, parse_dates=True)
df["m2_yoy_surge"] = df["m2_yoy"]

series_direction = {
    "yield_spread": -1, "sahm": +1, "cpi_yoy": +1, "m2_yoy_surge": +1,
    "vix": +1, "baa10y": +1, "oil_yoy": +1, "copper_yoy": -1, "houst_yoy": -1, "permit_yoy": -1,
    "mortgage_chg_12m": +1, "caseshiller_yoy": -1, "trade_balance_yoy_chg": -1,
}
ROLL = 60
zscores = pd.DataFrame(index=df.index)
for col, direction in series_direction.items():
    s = df[col]
    roll_mean = s.rolling(ROLL, min_periods=24).mean()
    roll_std = s.rolling(ROLL, min_periods=24).std()
    zscores[col] = (s - roll_mean) / roll_std * direction
anomaly = zscores > 2

# find every SPY drawdown episode of >=5%, recorded by its PEAK date (decline onset)
spy = df["spy"].dropna()
peak = spy.cummax()
dd = spy / peak - 1
THRESH = -0.05
in_dd, episodes = False, []
for d in dd.index:
    if dd.loc[d] <= THRESH and not in_dd:
        peak_val = peak.loc[d]
        peak_date = spy[spy == peak_val].index[-1]
        in_dd = True
        emin, tdate = dd.loc[d], d
    elif in_dd:
        if dd.loc[d] < emin:
            emin, tdate = dd.loc[d], d
        if dd.loc[d] > THRESH:
            episodes.append((peak_date, tdate, emin))
            in_dd = False
if in_dd:
    episodes.append((peak_date, tdate, emin))

# dedupe peaks that are the same all-time-high referenced multiple times in a row
seen_peaks = []
dedup = []
for p, t, m in episodes:
    if not seen_peaks or (p - seen_peaks[-1]).days > 60:
        dedup.append((p, t, m))
    seen_peaks.append(p)

print(f"SPY跌幅>=5%事件，共{len(dedup)}次:")
for p, t, m in dedup:
    print(f"  高點{p.strftime('%Y-%m')} 低點{t.strftime('%Y-%m')} 跌幅{m*100:.1f}%")

LOOKBACK = 2  # months
print(f"\n===== 高點前{LOOKBACK}個月內(含高點當月)，哪個指標已經異常 =====\n")
hit_counter = {c: 0 for c in series_direction}
for p, t, m in dedup:
    window_start = p - pd.DateOffset(months=LOOKBACK)
    window = anomaly.loc[window_start:p]
    fired = [c for c in series_direction if window[c].any()]
    for c in fired:
        hit_counter[c] += 1
    print(f"高點{p.strftime('%Y-%m')}(跌幅{m*100:.1f}%): {fired}")

print(f"\n===== 各指標在{len(dedup)}次事件中，「高點前{LOOKBACK}個月內」命中次數 =====")
summary = pd.Series(hit_counter).sort_values(ascending=False)
print(summary.to_string())
