"""
Build the Taiwan-side monthly indicator panel from the 6 confirmed-feasible raw sources
(see [[reference_macro_data_sources]]-style provenance: TWSE FMTQIK/MI_MARGN via direct curl,
FRED's handful of Taiwan-mirrored series). NDC's 景氣對策信號, CBC's CPI/M2/policy rate, and
TWSE's market-wide P/E are NOT in here yet - those are being collected manually by the user
and will be merged in once available. This script only uses what's already on disk.
"""
import pandas as pd
import numpy as np
import os

BASE = os.path.dirname(os.path.abspath(__file__))


def load_fred(name, col):
    df = pd.read_csv(os.path.join(BASE, f"{name}.csv"))
    df.columns = ["date", "value"]
    df["date"] = pd.to_datetime(df["date"])
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    s = df.dropna(subset=["value"]).set_index("date")["value"]
    s.name = col
    return s


# ---- TAIEX: daily close -> month-end close ----
taiex = pd.read_csv(os.path.join(BASE, "tw_taiex_daily.csv"), parse_dates=["date"]).set_index("date")["taiex_close"]
taiex_m = taiex.resample("ME").last()

# ---- margin debt: already monthly (one sampled day/month) ----
margin = pd.read_csv(os.path.join(BASE, "tw_margin_debt.csv"), parse_dates=["date"]).set_index("date")["margin_balance_thousand_ntd"]
margin_m = margin.resample("ME").last()

# ---- FRED Taiwan series ----
nasdaq_tw = load_fred("tw_nasdaq_largecap", "nasdaq_tw").resample("ME").last()
fx_usd = load_fred("tw_fx_usd", "fx_usd").resample("ME").last()
exports = load_fred("tw_exports", "exports").resample("ME").last()
imports = load_fred("tw_imports", "imports").resample("ME").last()
fx_reserves = load_fred("tw_fx_reserves", "fx_reserves").resample("ME").last()

df = pd.DataFrame({
    "taiex": taiex_m, "margin": margin_m, "nasdaq_tw": nasdaq_tw,
    "fx_usd": fx_usd, "exports": exports, "imports": imports, "fx_reserves": fx_reserves,
})

# ---- derived indicators (YoY % change, matching the US model's convention) ----
df["margin_yoy"] = df["margin"].pct_change(12) * 100
df["exports_yoy"] = df["exports"].pct_change(12) * 100
df["imports_yoy"] = df["imports"].pct_change(12) * 100
df["fx_usd_yoy"] = df["fx_usd"].pct_change(12) * 100         # TWD depreciation vs USD
df["fx_reserves_yoy"] = df["fx_reserves"].pct_change(12) * 100
df["trade_balance"] = df["exports"] - df["imports"]
df["trade_balance_yoy_chg"] = df["trade_balance"].diff(12)

df.to_csv(os.path.join(BASE, "tw_merged.csv"))
print(f"saved tw_merged.csv: {len(df)} rows, {df.index.min().date()} to {df.index.max().date()}")
print(df.tail(3).to_string())

# ---- identify TAIEX's own historical drawdown events (>=20% from trailing peak) ----
print("\n=== TAIEX historical drawdown episodes (>=20% from peak, deduplicated) ===")
peak = -np.inf
peak_date = None
in_drawdown = False
episodes = []
trough = np.inf
trough_date = None
for d, v in taiex_m.items():
    if v > peak:
        if in_drawdown and (peak - trough) / peak >= 0.20:
            episodes.append((peak_date, peak, trough_date, trough, (trough - peak) / peak * 100))
        peak = v
        peak_date = d
        in_drawdown = False
        trough = v
        trough_date = d
    else:
        dd = (v - peak) / peak
        if dd <= -0.05:
            in_drawdown = True
        if v < trough:
            trough = v
            trough_date = d
if in_drawdown and (peak - trough) / peak >= 0.20:
    episodes.append((peak_date, peak, trough_date, trough, (trough - peak) / peak * 100))

for peak_d, peak_v, trough_d, trough_v, pct in episodes:
    months = (trough_d.year - peak_d.year) * 12 + (trough_d.month - peak_d.month)
    print(f"  peak {peak_d.date()} ({peak_v:.0f}) -> trough {trough_d.date()} ({trough_v:.0f}): {pct:.1f}% over {months} months")
