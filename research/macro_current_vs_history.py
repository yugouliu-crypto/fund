import pandas as pd
import numpy as np
import os

BASE = os.path.dirname(os.path.abspath(__file__))
df = pd.read_csv(os.path.join(BASE, "macro_final.csv"), index_col=0, parse_dates=True)
df["m2_yoy_surge"] = df["m2_yoy"]

def load_fred(name):
    d = pd.read_csv(os.path.join(BASE, f"{name}.csv"))
    d.columns = ["date", "value"]
    d["date"] = pd.to_datetime(d["date"])
    d["value"] = pd.to_numeric(d["value"], errors="coerce")
    return d.dropna(subset=["value"]).set_index("date")["value"]

icsa = load_fred("ICSA").resample("ME").mean()
neworder = load_fred("NEWORDER").resample("ME").last()
nfci = load_fred("NFCI").resample("ME").last()
sloos = load_fred("DRTSCILM").resample("ME").last().ffill(limit=3)
df["icsa_yoy"] = icsa.pct_change(12) * 100
df["neworder_yoy"] = neworder.pct_change(12) * 100
df["nfci"] = nfci
df["sloos"] = sloos
margin = pd.read_csv(os.path.join(BASE, "finra_margin_clean.csv"), index_col=0, parse_dates=True)["debit_balance"]
df["margin_yoy"] = margin.resample("ME").last().reindex(df.index).pct_change(12) * 100

series_direction = {
    "yield_spread": -1, "sahm": +1, "cpi_yoy": +1, "m2_yoy_surge": +1, "margin_yoy": +1,
    "vix": +1, "baa10y": +1, "oil_yoy": +1, "copper_yoy": -1, "houst_yoy": -1, "permit_yoy": -1,
    "mortgage_chg_12m": +1, "caseshiller_yoy": -1, "trade_balance_yoy_chg": -1,
    "icsa_yoy": +1, "neworder_yoy": -1, "nfci": +1, "sloos": +1,
}
ROLL = 60
zscores = pd.DataFrame(index=df.index)
for col, direction in series_direction.items():
    s = df[col]
    roll_mean = s.rolling(ROLL, min_periods=24).mean()
    roll_std = s.rolling(ROLL, min_periods=24).std()
    zscores[col] = (s - roll_mean) / roll_std * direction

# each series reports on its own lag - some haven't posted a June value yet even though the
# merged frame's index extends to 2026-06 - so take each column's own last NON-NULL reading,
# not literally the dataframe's last row (same fix as the dashboard's tier cards needed).
current = zscores.apply(lambda s: s.dropna().iloc[-1] if s.dropna().size else np.nan)
current_month = zscores.apply(lambda s: s.dropna().index[-1].strftime("%Y-%m") if s.dropna().size else "-")
print("===== 現在(各指標取各自最新一筆)的Z分數 =====")
for k in current.sort_values(ascending=False).index:
    print(f"{k}: {current[k]:.2f}  ({current_month[k]})")

events = {
    "2000 dot-com": "2000-08", "2008 GFC": "2007-10", "1998 LTCM": "1998-06",
    "2016 mini修正": "2015-05", "2018 Q4賣壓": "2018-09", "2020 疫情": "2019-12",
    "2022 升息熊市": "2021-12",
}
print("\n===== 各次危機「高點前24個月」每個指標的最高Z分數，跟現在比 =====\n")
compare = pd.DataFrame(index=series_direction.keys())
compare["現在"] = current
for name, peak in events.items():
    peak_d = pd.Timestamp(peak + "-01") + pd.offsets.MonthEnd(0)
    window = zscores.loc[peak_d - pd.DateOffset(months=24):peak_d]
    compare[name] = window.max()

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 20)
print(compare.round(2).to_string())

print("\n===== 跟現在最相似的歷史時刻(用歐式距離排序,只比17個指標的Z分數向量) =====")
dist = {}
for name, peak in events.items():
    peak_d = pd.Timestamp(peak + "-01") + pd.offsets.MonthEnd(0)
    window = zscores.loc[peak_d - pd.DateOffset(months=24):peak_d]
    # for each historical month in the window, compute distance to "now"; report the closest
    diffs = (window - current.values).pow(2).sum(axis=1).pow(0.5)
    dist[name] = (diffs.min(), diffs.idxmin())
for name, (d, when) in sorted(dist.items(), key=lambda x: x[1][0]):
    print(f"{name}: 最相似的月份={when.strftime('%Y-%m')}, 距離={d:.2f}")
