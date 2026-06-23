import pandas as pd
import numpy as np
import os

BASE = os.path.dirname(os.path.abspath(__file__))
df = pd.read_csv(os.path.join(BASE, "macro_with_anomaly.csv"), index_col=0, parse_dates=True)
df["m2_yoy_surge"] = df["m2_yoy"]

spy = df["spy"]
for h, label in [(18, "18m"), (21, "21m"), (24, "24m")]:
    df[f"spy_fwd_{label}"] = spy.shift(-h) / spy - 1

series_direction = {"m2_yoy_surge": +1, "cpi_yoy": +1, "trade_balance_yoy_chg": -1}
ROLL = 60
zscores = pd.DataFrame(index=df.index)
for col, direction in series_direction.items():
    s = df[col]
    roll_mean = s.rolling(ROLL, min_periods=24).mean()
    roll_std = s.rolling(ROLL, min_periods=24).std()
    zscores[col] = (s - roll_mean) / roll_std * direction
anomaly = (zscores > 2)
df["combo3_count"] = anomaly.sum(axis=1)

FWD_COLS_EXT = ["spy_fwd_12m", "spy_fwd_18m", "spy_fwd_21m", "spy_fwd_24m"]
print("===== 同一組訊號，改用12/18/21/24個月視窗比較 =====")
combo = df.loc["1993-01-01":, ["combo3_count"] + FWD_COLS_EXT]
for n in sorted(combo["combo3_count"].dropna().unique()):
    sub = combo[combo["combo3_count"] == n]
    row = {"同時異常數": int(n), "月數": len(sub)}
    for col in FWD_COLS_EXT:
        vals = sub[col].dropna()
        row[col] = round(vals.mean() * 100, 2) if len(vals) else np.nan
    print(row)

print("\n===== 樣本外測試: 把30年切成兩半，分別看「2個以上異常」這個規則準不準 =====")
flag2plus = (df["combo3_count"] >= 2) & (df.index >= "1993-01-01")
for period_name, start, end in [("前半 1993-2009", "1993-01-01", "2009-12-31"), ("後半 2010-2026", "2010-01-01", "2026-12-31")]:
    sub_flag = flag2plus.loc[start:end]
    n_months_flagged = sub_flag.sum()
    vals = df.loc[sub_flag[sub_flag].index, "spy_fwd_12m"].dropna()
    print(f"{period_name}: 觸發月數={n_months_flagged}, 觸發後12個月平均報酬={vals.mean()*100:.1f}% (n={len(vals)})" if len(vals) else f"{period_name}: 觸發月數={n_months_flagged}, 無足夠資料")
