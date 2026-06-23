"""
Test the user's hypothesis directly: Taiwan's market should move with the US market, and the
already-validated US macro model (macro_final.csv / macro_zscores.csv from the US project) might
carry over as a leading signal for TAIEX too - reusing that work instead of rebuilding Taiwan's
own CPI/M2/valuation gate from scratch. Three checks: (1) raw return correlation of TAIEX vs
SPY vs SOX, (2) lead-lag cross-correlation to see who moves first, (3) whether the US model's
17 indicators' z-scores (already computed for SPY's crises) also spike ahead of TAIEX's own
named crisis windows.
"""
import pandas as pd
import numpy as np
import os

BASE = os.path.dirname(os.path.abspath(__file__))

taiex_m = pd.read_csv(os.path.join(BASE, "tw_taiex_daily.csv"), parse_dates=["date"]).set_index("date")["taiex_close"].resample("ME").last()
spy = pd.read_csv(os.path.join(BASE, "spy_monthly_since_inception.csv"), parse_dates=["date"]).set_index("date")["nav"].resample("ME").last()
sox = pd.read_csv(os.path.join(BASE, "tw_sox.csv"), parse_dates=["date"]).set_index("date")["sox"].resample("ME").last()
us = pd.read_csv(os.path.join(BASE, "macro_final.csv"), index_col=0, parse_dates=True)
us_z = pd.read_csv(os.path.join(BASE, "macro_zscores.csv"), index_col=0, parse_dates=True)

panel = pd.DataFrame({"taiex": taiex_m, "spy": spy, "sox": sox})
panel["taiex_ret"] = panel["taiex"].pct_change()
panel["spy_ret"] = panel["spy"].pct_change()
panel["sox_ret"] = panel["sox"].pct_change()

print("===== 1. 月報酬率相關係數 (整段重疊期間) =====")
overlap = panel.dropna(subset=["taiex_ret", "spy_ret", "sox_ret"])
print(f"重疊期間: {overlap.index.min().date()} ~ {overlap.index.max().date()}, {len(overlap)}個月")
print(f"TAIEX vs SPY 相關係數: {overlap['taiex_ret'].corr(overlap['spy_ret']):.3f}")
print(f"TAIEX vs SOX 相關係數: {overlap['taiex_ret'].corr(overlap['sox_ret']):.3f}")

print("\n===== 2. 領先/落後關係 (SPY/SOX領先TAIEX幾個月,相關係數最高?) =====")
for lag in range(-3, 4):
    c_spy = panel["taiex_ret"].corr(panel["spy_ret"].shift(lag))
    c_sox = panel["taiex_ret"].corr(panel["sox_ret"].shift(lag))
    direction = f"SPY/SOX領先{lag}個月" if lag > 0 else (f"TAIEX領先{-lag}個月" if lag < 0 else "同月")
    print(f"  lag={lag:+d} ({direction}): corr(TAIEX,SPY)={c_spy:.3f}  corr(TAIEX,SOX)={c_sox:.3f}")

print("\n===== 3. 美股模型17指標Z分數，套到TAIEX自己的危機事件上還準不準 =====")
taiex_d = pd.read_csv(os.path.join(BASE, "tw_taiex_daily.csv"), parse_dates=["date"]).set_index("date")["taiex_close"].dropna()
events = {
    "1997-98 亞洲金融風暴": ("1997-06-01", "1998-10-31"),
    "2000-01 網路泡沫": ("2000-01-01", "2001-10-31"),
    "2008 金融海嘯": ("2008-04-01", "2008-12-31"),
    "2011 歐債危機": ("2011-05-01", "2011-09-30"),
    "2015-16 中國放緩": ("2015-04-01", "2015-09-30"),
    "2018 Q4 賣壓": ("2018-05-01", "2018-11-30"),
    "2020 疫情": ("2020-01-01", "2020-04-30"),
    "2022 升息熊市": ("2021-12-01", "2022-10-31"),
}
current = us_z.apply(lambda s: s.dropna().iloc[-1] if s.dropna().size else np.nan)
current_month = us_z.apply(lambda s: s.dropna().index[-1].strftime("%Y-%m") if s.dropna().size else "-")
compare = pd.DataFrame(index=us_z.columns)
compare["現在(美股)"] = current
for name, (start, end) in events.items():
    peak_d = taiex_d[start:end].idxmax()
    peak_month_end = pd.Timestamp(peak_d).to_period("M").to_timestamp("M")
    window = us_z.loc[peak_month_end - pd.DateOffset(months=24):peak_month_end]
    compare[name] = window.max()
pd.set_option("display.width", 220)
pd.set_option("display.max_columns", 20)
print(compare.round(2).to_string())

print("\n===== 4. SOX本身在TAIEX危機高點前24個月的最大跌幅(同步/領先確認) =====")
sox_d_idx = sox.dropna()
for name, (start, end) in events.items():
    peak_d = taiex_d[start:end].idxmax()
    peak_month_end = pd.Timestamp(peak_d).to_period("M").to_timestamp("M")
    window_start = peak_month_end - pd.DateOffset(months=24)
    sox_window = sox_d_idx.loc[window_start:peak_month_end + pd.DateOffset(months=6)]
    if sox_window.empty:
        continue
    sox_peak = sox_window.loc[:peak_month_end].max() if not sox_window.loc[:peak_month_end].empty else np.nan
    sox_after = sox_window.loc[peak_month_end:]
    sox_trough = sox_after.min() if not sox_after.empty else np.nan
    if pd.notna(sox_peak) and pd.notna(sox_trough):
        print(f"  {name}: TAIEX高點{peak_month_end.date()}附近，SOX同期跌幅 {(sox_trough/sox_peak-1)*100:.1f}%")
