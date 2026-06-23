"""
Validate whether the Taiwan indicators secured so far (margin debt, exports/imports, TWD/USD,
FX reserves) show any pre-crisis anomaly pattern, using the same 60-month rolling z-score
methodology as the US model. Event windows below are the well-known named Taiwan/global crises;
peak-to-trough depth is measured directly off TAIEX daily data within each window, not assumed.
CPI/M2/景氣燈號/PE are not in here yet - pending the user's manual data collection.
"""
import pandas as pd
import numpy as np
import os

BASE = os.path.dirname(os.path.abspath(__file__))
df = pd.read_csv(os.path.join(BASE, "tw_merged.csv"), index_col=0, parse_dates=True)

direction = {
    "margin_yoy": +1, "exports_yoy": -1, "imports_yoy": -1,
    "fx_usd_yoy": +1, "fx_reserves_yoy": -1, "trade_balance_yoy_chg": -1,
}
ROLL = 60
z = pd.DataFrame(index=df.index)
for col, d in direction.items():
    s = df[col]
    roll_mean = s.rolling(ROLL, min_periods=24).mean()
    roll_std = s.rolling(ROLL, min_periods=24).std()
    z[col] = (s - roll_mean) / roll_std * d

current = z.apply(lambda s: s.dropna().iloc[-1] if s.dropna().size else np.nan)
current_month = z.apply(lambda s: s.dropna().index[-1].strftime("%Y-%m") if s.dropna().size else "-")
print("===== 現在(各指標取各自最新一筆)的Z分數 =====")
for k in current.sort_values(ascending=False).index:
    print(f"  {k}: {current[k]:.2f}  ({current_month[k]})")

# named windows: (label, search-start, search-end) - peak/trough found by argmax/argmin of TAIEX inside
taiex = pd.read_csv(os.path.join(BASE, "tw_taiex_daily.csv"), parse_dates=["date"]).set_index("date")["taiex_close"].dropna()
events = {
    "1990 泡沫破裂": ("1990-01-01", "1990-12-31"),
    "1997-98 亞洲金融風暴": ("1997-06-01", "1998-10-31"),
    "2000-01 網路泡沫": ("2000-01-01", "2001-10-31"),
    "2008 金融海嘯": ("2008-04-01", "2008-12-31"),
    "2011 歐債危機": ("2011-05-01", "2011-09-30"),
    "2015-16 中國放緩": ("2015-04-01", "2015-09-30"),
    "2018 Q4 賣壓": ("2018-05-01", "2018-11-30"),
    "2020 疫情": ("2020-01-01", "2020-04-30"),
    "2022 升息熊市": ("2021-12-01", "2022-10-31"),
}

print("\n===== 各次危機實際峰谷深度(直接從TAIEX日資料量出) + 高點前24個月各指標最高Z分數 =====\n")
compare = pd.DataFrame(index=direction.keys())
compare["現在"] = current
event_summaries = []
for name, (start, end) in events.items():
    window_px = taiex[start:end]
    if window_px.empty:
        continue
    peak_d = window_px.idxmax()
    peak_v = window_px.max()
    trough_window = taiex[peak_d:end]
    trough_d = trough_window.idxmin()
    trough_v = trough_window.min()
    pct = (trough_v - peak_v) / peak_v * 100
    event_summaries.append((name, peak_d, peak_v, trough_d, trough_v, pct))
    peak_month_end = pd.Timestamp(peak_d).to_period("M").to_timestamp("M")
    z_window = z.loc[peak_month_end - pd.DateOffset(months=24):peak_month_end]
    compare[name] = z_window.max()

for name, peak_d, peak_v, trough_d, trough_v, pct in event_summaries:
    print(f"{name}: 峰 {peak_d.date()}({peak_v:.0f}) -> 谷 {trough_d.date()}({trough_v:.0f})  {pct:.1f}%")

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 20)
print()
print(compare.round(2).to_string())
