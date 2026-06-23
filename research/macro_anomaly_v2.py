import pandas as pd
import numpy as np
import os

BASE = os.path.dirname(os.path.abspath(__file__))
df = pd.read_csv(os.path.join(BASE, "macro_with_anomaly.csv"), index_col=0, parse_dates=True)

# ---- fix: trade balance should be tested on its YoY *change* (already computed), not the raw
# level, since the level has a decades-long structural widening trend that isn't a "shock".
series_direction = {
    "yield_spread": -1,
    "sahm": +1,
    "cpi_yoy": +1,
    "m2_yoy_decline": -1,     # money supply growth collapsing = stress
    "m2_yoy_surge": +1,       # money supply growth surging = future-inflation-risk signal
    "vix": +1,
    "baa10y": +1,
    "oil_yoy": +1,
    "copper_yoy": -1,
    "houst_yoy": -1,
    "permit_yoy": -1,
    "mortgage_chg_12m": +1,
    "caseshiller_yoy": -1,
    "trade_balance_yoy_chg": -1,  # fixed: sudden widening of the deficit, not the chronic level
}
df["m2_yoy_decline"] = df["m2_yoy"]
df["m2_yoy_surge"] = df["m2_yoy"]

ROLL = 60
zscores = pd.DataFrame(index=df.index)
for col, direction in series_direction.items():
    s = df[col]
    roll_mean = s.rolling(ROLL, min_periods=24).mean()
    roll_std = s.rolling(ROLL, min_periods=24).std()
    zscores[col] = (s - roll_mean) / roll_std * direction

anomaly = (zscores > 2)
df["anomaly_count_v2"] = anomaly.sum(axis=1)

print("===== 修正後 trade_balance_yoy_chg 異常年份(應該變成短暫尖峰,不是長期連續) =====")
months = df.index[anomaly["trade_balance_yoy_chg"].fillna(False)]
print(sorted(set(m.year for m in months)))

print("\n===== M2_surge(貨幣供給暴增,預示未來通膨風險) 異常年份 =====")
months = df.index[anomaly["m2_yoy_surge"].fillna(False)]
print(sorted(set(m.year for m in months)))

print("\n\n===== 2020-07 到 2022-06 這段時間，逐月列出哪些指標當月正處於異常(z>2) =====")
window = anomaly.loc["2020-07":"2022-06"]
spy_window = df.loc["2020-07":"2022-06", "spy"]
for d in window.index:
    active = [c for c in window.columns if window.loc[d, c]]
    spy_val = spy_window.loc[d]
    if active:
        print(f"{d.strftime('%Y-%m')} (SPY={spy_val:.0f}): {', '.join(active)}")

print("\n===== 對照: SPY實際走勢與2022真正高點 =====")
spy_2021_2022 = df.loc["2021-01":"2022-12", "spy"]
peak_date = spy_2021_2022.idxmax()
print(f"2021-2022這段SPY最高點: {peak_date.strftime('%Y-%m')}, 值={spy_2021_2022.max():.0f}")
print(spy_2021_2022.to_string())
