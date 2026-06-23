import pandas as pd
import numpy as np
import os

BASE = os.path.dirname(os.path.abspath(__file__))

def load_fred(name, value_col):
    df = pd.read_csv(os.path.join(BASE, f"{name}.csv"))
    df.columns = ["date", "value"]
    df["date"] = pd.to_datetime(df["date"])
    df["value"] = pd.to_numeric(df["value"], errors="coerce")  # FRED uses "." for missing
    df = df.dropna(subset=["value"]).set_index("date")["value"]
    df.name = value_col
    return df

# ---- load all indicators, resample to month-end (using last available value in the month) ----
dgs10 = load_fred("DGS10", "dgs10").resample("ME").last()
dgs2 = load_fred("DGS2", "dgs2").resample("ME").last()
unrate = load_fred("UNRATE", "unrate").resample("ME").last()
cpi = load_fred("CPIAUCSL", "cpi").resample("ME").last()
m2 = load_fred("M2SL", "m2").resample("ME").last()
vix = load_fred("VIXCLS", "vix").resample("ME").last()
baa10y = load_fred("BAA10Y", "baa10y").resample("ME").last()
oil = load_fred("DCOILWTICO", "oil").resample("ME").last()
copper = load_fred("PCOPPUSDM", "copper").resample("ME").last()
houst = load_fred("HOUST", "houst").resample("ME").last()
permit = load_fred("PERMIT", "permit").resample("ME").last()
mortgage = load_fred("MORTGAGE30US", "mortgage").resample("ME").last()
caseshiller = load_fred("CSUSHPISA", "caseshiller").resample("ME").last()

spy = pd.read_csv(os.path.join(BASE, "spy_monthly_since_inception.csv"))
spy["date"] = pd.to_datetime(spy["date"])
spy = spy.set_index("date")["nav"].resample("ME").last()
spy.name = "spy"

# ---- merge everything onto one monthly index ----
df = pd.concat([dgs10, dgs2, unrate, cpi, m2, vix, baa10y, oil, copper, houst, permit, mortgage, caseshiller, spy], axis=1)
df = df.sort_index()

# ---- derive indicators ----
df["yield_spread"] = df["dgs10"] - df["dgs2"]
df["unrate_3ma"] = df["unrate"].rolling(3).mean()
df["sahm"] = df["unrate_3ma"] - df["unrate_3ma"].rolling(12).min()
df["cpi_yoy"] = df["cpi"].pct_change(12) * 100
df["m2_yoy"] = df["m2"].pct_change(12) * 100
df["oil_yoy"] = df["oil"].pct_change(12) * 100
df["copper_yoy"] = df["copper"].pct_change(12) * 100
df["houst_yoy"] = df["houst"].pct_change(12) * 100
df["permit_yoy"] = df["permit"].pct_change(12) * 100
df["caseshiller_yoy"] = df["caseshiller"].pct_change(12) * 100
df["mortgage_chg_12m"] = df["mortgage"].diff(12)

# ---- forward SPY returns ----
for h, label in [(1, "1m"), (3, "3m"), (6, "6m"), (12, "12m")]:
    df[f"spy_fwd_{label}"] = df["spy"].shift(-h) / df["spy"] - 1

df.to_csv(os.path.join(BASE, "macro_merged.csv"))
print("rows:", len(df))
print("date range:", df.index.min(), "~", df.index.max())
print(df[["yield_spread", "sahm", "cpi_yoy", "m2_yoy", "vix", "baa10y", "oil_yoy", "houst_yoy"]].dropna(how="all").tail(3))
