import pandas as pd
import numpy as np
import os

BASE = os.path.dirname(os.path.abspath(__file__))
df = pd.read_csv(os.path.join(BASE, "macro_with_anomaly.csv"), index_col=0, parse_dates=True)
df["m2_yoy_surge"] = df["m2_yoy"]
df["m2_yoy_decline"] = df["m2_yoy"]

def load_fred(name):
    d = pd.read_csv(os.path.join(BASE, f"{name}.csv"))
    d.columns = ["date", "value"]
    d["date"] = pd.to_datetime(d["date"])
    d["value"] = pd.to_numeric(d["value"], errors="coerce")
    return d.dropna(subset=["value"]).set_index("date")["value"]

icsa = load_fred("ICSA").resample("ME").mean()  # weekly -> monthly average
neworder = load_fred("NEWORDER").resample("ME").last()

df["icsa"] = icsa
df["neworder"] = neworder
df["icsa_yoy"] = df["icsa"].pct_change(12) * 100
df["neworder_yoy"] = df["neworder"].pct_change(12) * 100

series_direction = {
    "yield_spread": -1, "sahm": +1, "cpi_yoy": +1, "m2_yoy_decline": -1, "m2_yoy_surge": +1,
    "vix": +1, "baa10y": +1, "oil_yoy": +1, "copper_yoy": -1, "houst_yoy": -1, "permit_yoy": -1,
    "mortgage_chg_12m": +1, "caseshiller_yoy": -1, "trade_balance_yoy_chg": -1,
    "icsa_yoy": +1,        # initial claims rising sharply = labor market weakening
    "neworder_yoy": -1,    # durable goods new orders falling = manufacturing/PMI-proxy weakening
}

ROLL = 60
zscores = pd.DataFrame(index=df.index)
for col, direction in series_direction.items():
    s = df[col]
    roll_mean = s.rolling(ROLL, min_periods=24).mean()
    roll_std = s.rolling(ROLL, min_periods=24).std()
    zscores[col] = (s - roll_mean) / roll_std * direction
anomaly = zscores > 2

events = {
    "1998 LTCM": "1998-06", "2000 dot-com": "2000-08", "2008 GFC": "2007-10",
    "2016 mini修正": "2015-05", "2018 Q4賣壓": "2018-09", "2020 疫情": "2019-12",
    "2022 升息熊市": "2021-12",
}

LOOKBACK_MONTHS = 24
matrix = pd.DataFrame(index=events.keys(), columns=series_direction.keys(), data=False)
for ev_name, peak_str in events.items():
    peak = pd.Timestamp(peak_str + "-01") + pd.offsets.MonthEnd(0)
    window_start = peak - pd.DateOffset(months=LOOKBACK_MONTHS)
    window = anomaly.loc[window_start:peak]
    fired = [c for c in series_direction if window[c].any()]
    for c in fired:
        matrix.loc[ev_name, c] = True
    print(f"{ev_name} (高點{peak_str}): {fired}")

print("\n===== 加入ICSA/NEWORDER後，每個指標命中次數(滿分7) =====")
counts = matrix.sum(axis=0).sort_values(ascending=False)
print(counts.to_string())

print("\n===== ICSA/NEWORDER 各自的異常年份 =====")
for col in ["icsa_yoy", "neworder_yoy"]:
    months = df.index[anomaly[col].fillna(False)]
    print(f"{col}: {sorted(set(m.year for m in months))}")
