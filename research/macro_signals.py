import pandas as pd
import numpy as np
import os

BASE = os.path.dirname(os.path.abspath(__file__))
df = pd.read_csv(os.path.join(BASE, "macro_merged.csv"), index_col=0, parse_dates=True)

FWD_COLS = ["spy_fwd_1m", "spy_fwd_3m", "spy_fwd_6m", "spy_fwd_12m"]

def trigger_dates(series, condition):
    """first month a (previously-false) condition becomes true - one event per episode."""
    cond = condition(series).fillna(False)
    prev = cond.shift(1).fillna(False)
    return series.index[cond & ~prev]

def summarize(name, dates, df, baseline):
    rows = []
    for h, col in zip(["1m", "3m", "6m", "12m"], FWD_COLS):
        vals = df.loc[df.index.isin(dates), col].dropna()
        base = baseline[col].dropna()
        rows.append({
            "indicator": name, "horizon": h, "n_events": len(vals),
            "avg_fwd_return": vals.mean() * 100 if len(vals) else np.nan,
            "pct_positive": (vals > 0).mean() * 100 if len(vals) else np.nan,
            "baseline_avg": base.mean() * 100,
            "baseline_pct_positive": (base > 0).mean() * 100,
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

all_rows = []
for name, (series, cond) in signals.items():
    dates = trigger_dates(series, cond)
    rows = summarize(name, dates, df, df)
    all_rows.extend(rows)

result = pd.DataFrame(all_rows)
result.to_csv(os.path.join(BASE, "macro_signal_results.csv"), index=False, encoding="utf-8-sig")

pd.set_option("display.width", 160)
pd.set_option("display.max_columns", 20)
for name in signals:
    sub = result[result["indicator"] == name]
    n = sub["n_events"].iloc[0]
    print(f"\n=== {name} (觸發次數={n}) ===")
    print(sub[["horizon", "avg_fwd_return", "pct_positive", "baseline_avg", "baseline_pct_positive"]].to_string(index=False))
