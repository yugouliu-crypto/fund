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

nikkei = load_fred("NIKKEI225").resample("ME").last()
cpi_monthly = load_fred("JPNCPIALLMINMEI").resample("ME").last()  # index level, stops 2021-06
cpi_annual_pct = load_fred("FPCPITOTLZGJPN")  # already annual % change, through 2024
m3 = load_fred("MABMM301JPM189S").resample("ME").last()  # stops 2023-11

df = pd.DataFrame(index=nikkei.index)
df["nikkei"] = nikkei
df["cpi_level"] = cpi_monthly
df["m3"] = m3

# cpi_yoy from the monthly index where available; fill remaining months from the annual % series
df["cpi_yoy_monthly"] = df["cpi_level"].pct_change(12) * 100
cpi_annual_monthly = cpi_annual_pct.reindex(df.index, method="ffill")
df["cpi_yoy"] = df["cpi_yoy_monthly"].combine_first(cpi_annual_monthly)
df["m3_yoy"] = df["m3"].pct_change(12) * 100

for h, label in [(1, "1m"), (3, "3m"), (6, "6m"), (12, "12m"), (24, "24m")]:
    df[f"nikkei_fwd_{label}"] = df["nikkei"].shift(-h) / df["nikkei"] - 1

df.to_csv(os.path.join(BASE, "macro_japan_merged.csv"))
print("date range:", df.index.min(), "~", df.index.max())
print("cpi_yoy 涵蓋:", df["cpi_yoy"].dropna().index.min(), "~", df["cpi_yoy"].dropna().index.max())
print("m3_yoy 涵蓋:", df["m3_yoy"].dropna().index.min(), "~", df["m3_yoy"].dropna().index.max())

# ---- anomaly detection, same z-score logic as the US model ----
series_direction = {"cpi_yoy": +1, "m3_yoy": +1}
ROLL = 60
zscores = pd.DataFrame(index=df.index)
for col, direction in series_direction.items():
    s = df[col]
    roll_mean = s.rolling(ROLL, min_periods=24).mean()
    roll_std = s.rolling(ROLL, min_periods=24).std()
    zscores[col] = (s - roll_mean) / roll_std * direction
anomaly = zscores > 2

print("\n===== 日本 CPI/M3 異常年份 =====")
for col in series_direction:
    months = df.index[anomaly[col].fillna(False)]
    print(f"{col}: {sorted(set(m.year for m in months))}")

df["jp_anomaly_count"] = anomaly.sum(axis=1)
FWD = ["nikkei_fwd_1m", "nikkei_fwd_3m", "nikkei_fwd_6m", "nikkei_fwd_12m", "nikkei_fwd_24m"]
print("\n===== 日經指數: 異常數 vs 接下來表現 =====")
combo = df[["jp_anomaly_count"] + FWD]
for n in sorted(combo["jp_anomaly_count"].dropna().unique()):
    sub = combo[combo["jp_anomaly_count"] == n]
    row = {"異常數": int(n), "月數": len(sub)}
    for c in FWD:
        vals = sub[c].dropna()
        row[c] = round(vals.mean() * 100, 1) if len(vals) else np.nan
    print(row)

# ---- Nikkei's own drawdown history for periodicity cross-check ----
peak = df["nikkei"].cummax()
dd = df["nikkei"] / peak - 1
THRESH = -0.15
in_dd = False
episodes = []
for d in dd.dropna().index:
    if dd.loc[d] <= THRESH and not in_dd:
        peak_val = peak.loc[d]
        peak_date = df["nikkei"][df["nikkei"] == peak_val].index[-1]
        in_dd = True
        emin = dd.loc[d]; tdate = d
    elif in_dd:
        if dd.loc[d] < emin:
            emin = dd.loc[d]; tdate = d
        if dd.loc[d] > THRESH:
            episodes.append((peak_date, tdate, emin)); in_dd = False
if in_dd:
    episodes.append((peak_date, tdate, emin))

print("\n===== 日經指數 1949-2026 跌幅超過15%事件 =====")
prev = None
for p, t, m in episodes:
    gap = (t - prev).days / 365.25 if prev else None
    print(f"高點{p.strftime('%Y-%m')} -> 低點{t.strftime('%Y-%m')}  跌幅{m*100:.1f}%" + (f"  距上次低點{gap:.1f}年" if gap else ""))
    prev = t
