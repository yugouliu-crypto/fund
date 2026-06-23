import pandas as pd
import numpy as np
import os

BASE = os.path.dirname(os.path.abspath(__file__))
df = pd.read_csv(os.path.join(BASE, "macro_with_anomaly.csv"), index_col=0, parse_dates=True)
df["m2_yoy_surge"] = df["m2_yoy"]

series_direction = {
    "m2_yoy_surge": +1,            # M2 growth spiking = future inflation/instability risk
    "cpi_yoy": +1,                 # inflation surge
    "trade_balance_yoy_chg": -1,   # trade deficit suddenly widening
}

ROLL = 60
zscores = pd.DataFrame(index=df.index)
for col, direction in series_direction.items():
    s = df[col]
    roll_mean = s.rolling(ROLL, min_periods=24).mean()
    roll_std = s.rolling(ROLL, min_periods=24).std()
    zscores[col] = (s - roll_mean) / roll_std * direction

anomaly = (zscores > 2)
df["combo3_count"] = anomaly.sum(axis=1)
FWD_COLS = ["spy_fwd_1m", "spy_fwd_3m", "spy_fwd_6m", "spy_fwd_12m"]

print("===== 限定SPY有資料的1993年後，這3個指標各自的異常年份 =====")
for col in series_direction:
    months = df.index[anomaly[col].fillna(False) & (df.index >= "1993-01-01")]
    print(f"{col}: {sorted(set(m.year for m in months))}")

print("\n===== M2+CPI+貿易順逆差 組合，依「同時異常數」分組的SPY後續報酬(1993年後) =====")
combo = df.loc["1993-01-01":, ["combo3_count"] + FWD_COLS]
for n in sorted(combo["combo3_count"].dropna().unique()):
    sub = combo[combo["combo3_count"] == n]
    row = {"同時異常數": int(n), "月數": len(sub)}
    for h, c in zip(["1m", "3m", "6m", "12m"], FWD_COLS):
        vals = sub[c].dropna()
        row[f"avg_{h}"] = round(vals.mean() * 100, 2) if len(vals) else np.nan
        row[f"pct_pos_{h}"] = round((vals > 0).mean() * 100, 1) if len(vals) else np.nan
    print(row)

print("\n===== 找出「3個全部同時異常」或「至少2個同時異常」的完整事件清單(去重成連續區段) =====")
flag2plus = (df["combo3_count"] >= 2) & (df.index >= "1993-01-01")
in_ep = False
episodes = []
for d in df.index[df.index >= "1993-01-01"]:
    f = flag2plus.loc[d]
    if f and not in_ep:
        start = d
        in_ep = True
    if not f and in_ep:
        episodes.append((start, prev_d))
        in_ep = False
    prev_d = d
if in_ep:
    episodes.append((start, prev_d))

for start, end in episodes:
    active_cols = [c for c in series_direction if anomaly.loc[start, c]]
    spy_before = df.loc[start, "spy"]
    fwd12 = df.loc[start, "spy_fwd_12m"]
    print(f"{start.strftime('%Y-%m')} ~ {end.strftime('%Y-%m')}  起始時異常指標={active_cols}  起始SPY={spy_before:.0f}  起始後12個月報酬={fwd12*100:.1f}%" if pd.notna(fwd12) else
          f"{start.strftime('%Y-%m')} ~ {end.strftime('%Y-%m')}  起始時異常指標={active_cols}  起始SPY={spy_before:.0f}  起始後12個月報酬=資料不足")
