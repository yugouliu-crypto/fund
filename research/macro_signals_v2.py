import pandas as pd
import numpy as np
import os

BASE = os.path.dirname(os.path.abspath(__file__))
df = pd.read_csv(os.path.join(BASE, "macro_merged.csv"), index_col=0, parse_dates=True)
FWD_COLS = ["spy_fwd_1m", "spy_fwd_3m", "spy_fwd_6m", "spy_fwd_12m"]

def episode_dates(series, condition, cooldown_months=6):
    """First month of each *episode*: consecutive trigger-months collapse into one event,
    and we also require `cooldown_months` of non-trigger before counting a new episode,
    so a signal that flickers on/off near a threshold doesn't get double-counted."""
    cond = condition(series).fillna(False)
    dates = []
    last_episode_end = None
    in_episode = False
    idx = series.index
    for i, d in enumerate(idx):
        if cond.iloc[i]:
            if not in_episode:
                if last_episode_end is None or (d - last_episode_end).days > cooldown_months * 30:
                    dates.append(d)
                in_episode = True
        else:
            if in_episode:
                last_episode_end = idx[i - 1]
            in_episode = False
    return pd.DatetimeIndex(dates)

def own_baseline(series, df):
    """restrict the baseline to the same date range where this specific indicator has data."""
    valid_range = series.dropna().index
    if len(valid_range) == 0:
        return df[FWD_COLS]
    return df.loc[(df.index >= valid_range.min()) & (df.index <= valid_range.max()), FWD_COLS]

def summarize(name, dates, df, baseline_df):
    rows = []
    for h, col in zip(["1m", "3m", "6m", "12m"], FWD_COLS):
        vals = df.loc[df.index.isin(dates), col].dropna()
        base = baseline_df[col].dropna()
        rows.append({
            "indicator": name, "horizon": h, "n_episodes": len(vals),
            "avg_fwd_return": round(vals.mean() * 100, 2) if len(vals) else np.nan,
            "pct_positive": round((vals > 0).mean() * 100, 1) if len(vals) else np.nan,
            "baseline_avg": round(base.mean() * 100, 2),
            "baseline_pct_positive": round((base > 0).mean() * 100, 1),
            "edge_vs_baseline": round((vals.mean() - base.mean()) * 100, 2) if len(vals) else np.nan,
        })
    return rows

signals = {
    "殖利率倒掛(10Y-2Y轉負)": (df["yield_spread"], lambda s: s < 0),
    "Sahm_Rule觸發(失業率)": (df["sahm"], lambda s: s >= 0.5),
    "CPI年增率突破5%": (df["cpi_yoy"], lambda s: s > 5),
    "M2年增率轉負": (df["m2_yoy"], lambda s: s < 0),
    "VIX突破30": (df["vix"], lambda s: s > 30),
    "信用價差(Baa-10Y)年增超過1個百分點": (df["baa10y"].diff(12), lambda s: s > 1),
    "油價年增超過50%": (df["oil_yoy"], lambda s: s > 50),
    "新屋開工年減超過20%": (df["houst_yoy"], lambda s: s < -20),
    "建照年減超過20%": (df["permit_yoy"], lambda s: s < -20),
    "房貸利率12月內漲超過1.5個百分點": (df["mortgage_chg_12m"], lambda s: s > 1.5),
    "房價(Case-Shiller)年增率轉負": (df["caseshiller_yoy"], lambda s: s < 0),
}

episodes_by_signal = {}
all_rows = []
for name, (series, cond) in signals.items():
    dates = episode_dates(series, cond, cooldown_months=6)
    episodes_by_signal[name] = dates
    baseline_df = own_baseline(series, df)
    rows = summarize(name, dates, df, baseline_df)
    all_rows.extend(rows)

result = pd.DataFrame(all_rows)
result.to_csv(os.path.join(BASE, "macro_signal_results_v2.csv"), index=False, encoding="utf-8-sig")

print("===== 修正後(事件去重+各自基準) =====")
for name in signals:
    sub = result[result["indicator"] == name]
    n = sub["n_episodes"].iloc[0]
    dates = episodes_by_signal[name]
    date_list = ", ".join(d.strftime("%Y-%m") for d in dates) if len(dates) <= 12 else f"{len(dates)}次(太多列不完)"
    print(f"\n=== {name} (事件數={n}) ===")
    print("事件時間點:", date_list)
    print(sub[["horizon", "avg_fwd_return", "edge_vs_baseline", "pct_positive", "baseline_pct_positive"]].to_string(index=False))

# ---- combination test: how many signals are "active" (within their post-trigger window) at each month ----
WINDOW_MONTHS = 12
active_flags = pd.DataFrame(index=df.index)
for name, dates in episodes_by_signal.items():
    flag = pd.Series(False, index=df.index)
    for d in dates:
        flag.loc[(df.index >= d) & (df.index < d + pd.DateOffset(months=WINDOW_MONTHS))] = True
    active_flags[name] = flag

active_flags["n_active"] = active_flags.sum(axis=1)
combo = pd.concat([active_flags["n_active"], df[FWD_COLS]], axis=1)

print("\n\n===== 同時有幾個訊號在「觸發後12個月窗口內」，SPY後續表現 =====")
for n in sorted(combo["n_active"].unique()):
    sub = combo[combo["n_active"] == n]
    row = {"n_signals_active": n, "n_months": len(sub)}
    for h, col in zip(["1m", "3m", "6m", "12m"], FWD_COLS):
        vals = sub[col].dropna()
        row[f"avg_{h}"] = round(vals.mean() * 100, 2) if len(vals) else np.nan
    print(row)
