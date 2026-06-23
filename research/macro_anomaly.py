import pandas as pd
import numpy as np
import os

BASE = os.path.dirname(os.path.abspath(__file__))

def load_fred(name):
    df = pd.read_csv(os.path.join(BASE, f"{name}.csv"))
    df.columns = ["date", "value"]
    df["date"] = pd.to_datetime(df["date"])
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df.dropna(subset=["value"]).set_index("date")["value"]

# reuse the monthly merge already built, then add trade data
df = pd.read_csv(os.path.join(BASE, "macro_merged.csv"), index_col=0, parse_dates=True)
bopgstb = load_fred("BOPGSTB").resample("ME").last()
netexp = load_fred("NETEXP").resample("ME").last().ffill(limit=2)  # quarterly -> forward-filled monthly
df["bopgstb"] = bopgstb
df["netexp"] = netexp
df["trade_balance_yoy_chg"] = df["bopgstb"].diff(12)

# series to test, and which direction signals stress (we z-score that direction so +2 always = "bad/unusual")
series_direction = {
    "yield_spread": -1,      # very negative spread (deep inversion) = stress
    "sahm": +1,              # rising unemployment = stress
    "cpi_yoy": +1,           # inflation surge = stress
    "m2_yoy": -1,            # collapsing money supply growth = stress
    "vix": +1,               # fear spike = stress (but historically marks bottoms, not tops)
    "baa10y": +1,            # widening credit spread = stress
    "oil_yoy": +1,           # oil price spike = stress
    "copper_yoy": -1,        # falling copper = weakening demand = stress
    "houst_yoy": -1,         # housing starts collapsing = stress
    "permit_yoy": -1,
    "mortgage_chg_12m": +1,  # mortgage rate spiking = stress
    "caseshiller_yoy": -1,   # home prices falling = stress
    "bopgstb": -1,           # trade deficit widening (more negative) = stress
}

ROLL = 60  # 5-year rolling window for the z-score baseline (lets "normal" adapt across eras)
zscores = pd.DataFrame(index=df.index)
for col, direction in series_direction.items():
    s = df[col]
    roll_mean = s.rolling(ROLL, min_periods=24).mean()
    roll_std = s.rolling(ROLL, min_periods=24).std()
    z = (s - roll_mean) / roll_std * direction
    zscores[col] = z

anomaly = (zscores > 2)
df["anomaly_count"] = anomaly.sum(axis=1)
zscores.to_csv(os.path.join(BASE, "macro_zscores.csv"))

FWD_COLS = ["spy_fwd_1m", "spy_fwd_3m", "spy_fwd_6m", "spy_fwd_12m"]

print("===== 各指標 Z>2 異常的月份(以年份列出，方便交叉比對) =====")
per_indicator_years = {}
for col in series_direction:
    months = df.index[anomaly[col].fillna(False)]
    years = sorted(set(m.year for m in months))
    per_indicator_years[col] = years
    print(f"{col}: {years}")

print("\n===== 異常數最多的前20個月份(交叉比對結果) =====")
top = df[["anomaly_count"] + FWD_COLS].dropna(subset=["anomaly_count"]).sort_values("anomaly_count", ascending=False).head(20)
print(top.to_string())

print("\n===== 按「同時異常指標數」分組，SPY後續報酬 =====")
combo = df[["anomaly_count"] + FWD_COLS]
for n in sorted(combo["anomaly_count"].dropna().unique()):
    sub = combo[combo["anomaly_count"] == n]
    row = {"異常指標數": int(n), "月數": len(sub)}
    for h, c in zip(["1m", "3m", "6m", "12m"], FWD_COLS):
        vals = sub[c].dropna()
        row[f"avg_{h}"] = round(vals.mean() * 100, 2) if len(vals) else np.nan
    print(row)

df.to_csv(os.path.join(BASE, "macro_with_anomaly.csv"))
