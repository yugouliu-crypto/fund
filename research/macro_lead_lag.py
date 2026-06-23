import pandas as pd
import numpy as np
import os

BASE = os.path.dirname(os.path.abspath(__file__))
df = pd.read_csv(os.path.join(BASE, "macro_final.csv"), index_col=0, parse_dates=True)

series_direction = {
    "yield_spread": -1, "sahm": +1, "cpi_yoy": +1, "m2_yoy": +1, "vix": +1, "baa10y": +1,
    "oil_yoy": +1, "copper_yoy": -1, "houst_yoy": -1, "permit_yoy": -1, "mortgage_chg_12m": +1,
    "caseshiller_yoy": -1, "trade_balance_yoy_chg": -1, "icsa_yoy": +1, "neworder_yoy": -1,
    "nfci": +1, "sloos": +1,
}

ROLL = 60
zscores = pd.DataFrame(index=df.index)
for col, direction in series_direction.items():
    s = df[col]
    roll_mean = s.rolling(ROLL, min_periods=24).mean()
    roll_std = s.rolling(ROLL, min_periods=24).std()
    zscores[col] = (s - roll_mean) / roll_std * direction
anomaly = zscores > 2

def episode_starts(col, cooldown_months=12):
    cond = anomaly[col].fillna(False)
    starts = []
    last_end = None
    in_ep = False
    idx = cond.index
    for i, d in enumerate(idx):
        if cond.iloc[i]:
            if not in_ep:
                if last_end is None or (d - last_end).days > cooldown_months * 30:
                    starts.append(d)
                in_ep = True
        else:
            if in_ep:
                last_end = idx[i - 1]
            in_ep = False
    return starts

cpi_starts = [d for d in episode_starts("cpi_yoy") if d >= pd.Timestamp("1990-01-01")]
print("CPI年增率異常的獨立事件起點(1990年後):", [d.strftime("%Y-%m") for d in cpi_starts])

LOOKBACK = 24
print(f"\n===== 每次CPI異常開始前{LOOKBACK}個月內，哪些其他指標已經先異常、提前幾個月 =====\n")
lead_records = {col: [] for col in series_direction if col != "cpi_yoy"}
for cpi_d in cpi_starts:
    window_start = cpi_d - pd.DateOffset(months=LOOKBACK)
    print(f"--- CPI異常開始於 {cpi_d.strftime('%Y-%m')} ---")
    for col in series_direction:
        if col == "cpi_yoy":
            continue
        window = anomaly.loc[window_start:cpi_d, col].fillna(False)
        fired_dates = window.index[window]
        if len(fired_dates) > 0:
            first_fire = fired_dates[0]
            lead_months = (cpi_d - first_fire).days / 30.4
            lead_records[col].append(lead_months)
            print(f"  {col}: 提前 {lead_months:.0f} 個月 (首次異常於{first_fire.strftime('%Y-%m')})")

print("\n===== 總結: 各指標在CPI異常前出現過的次數與平均提前月數 =====")
summary = []
for col, leads in lead_records.items():
    if leads:
        summary.append({"指標": col, "命中次數": len(leads), "平均提前月數": round(np.mean(leads), 1)})
summary_df = pd.DataFrame(summary).sort_values(["命中次數", "平均提前月數"], ascending=[False, False])
print(summary_df.to_string(index=False))
