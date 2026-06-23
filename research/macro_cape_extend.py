import pandas as pd
import numpy as np
import os

BASE = os.path.dirname(os.path.abspath(__file__))

# ---- reload Shiller's raw columns (need nominal P, E, CPI, real P, real E) ----
shiller = pd.read_excel(os.path.join(BASE, "shiller_ie_data.xls"), sheet_name="Data", skiprows=7)
shiller = shiller.dropna(subset=["Date"])
shiller = shiller[shiller["Date"].apply(lambda x: isinstance(x, (int, float)))]
shiller["year"] = shiller["Date"].apply(lambda x: int(x))
shiller["month"] = shiller["Date"].apply(lambda x: round((x - int(x)) * 100)).replace(0, 1)
shiller["date"] = pd.to_datetime(dict(year=shiller["year"], month=shiller["month"], day=1))
shiller = shiller.set_index("date")
# columns: P=nominal price, E=nominal 10yr-avg earnings, CPI=his own CPI index, "Price.1"/"Earnings.1" = real (inflation-adjusted) versions
shiller = shiller.rename(columns={"P": "nom_price", "E": "nom_e10", "Price.1": "real_price", "Earnings.1": "real_e10", "CAPE": "cape"})
for c in ["nom_price", "nom_e10", "real_price", "real_e10", "cape"]:
    shiller[c] = pd.to_numeric(shiller[c], errors="coerce")
shiller = shiller[["nom_price", "nom_e10", "real_price", "real_e10", "cape"]].dropna(subset=["cape"])
# the raw earnings columns are blank for the last few months Shiller publishes (reported EPS lags
# the price by a quarter+), even though "cape" itself is populated - so derive real_e10/nom_e10
# directly from cape = real_price / real_e10 wherever the raw columns are missing.
shiller["real_e10"] = shiller["real_e10"].fillna(shiller["real_price"] / shiller["cape"])
shiller["nom_e10"] = shiller["nom_e10"].fillna(shiller["nom_price"] / shiller["cape"])
last_shiller_date = shiller.index.max()
print("Shiller資料最後一筆:", last_shiller_date, "\n", shiller.loc[last_shiller_date])

# ---- our own data: SPY nominal price + CPI ----
df = pd.read_csv(os.path.join(BASE, "macro_final.csv"), index_col=0, parse_dates=True)
spy = df["spy"]
cpi = df["cpi"]  # CPIAUCSL index level, already in macro_final.csv

# calibrate: at the splice month, our SPY price vs Shiller's nominal price may differ in scale
# (different index construction/dividend conventions) - find the ratio at the splice point.
splice_month = last_shiller_date
spy_at_splice = spy.loc[splice_month] if splice_month in spy.index else spy.asof(splice_month)
shiller_price_at_splice = shiller.loc[splice_month, "nom_price"]
scale = shiller_price_at_splice / spy_at_splice
print(f"\n校準比例(Shiller nominal price / 我們的SPY): {scale:.4f} (在{splice_month})")

# extend nominal price forward using our SPY series, scaled to match Shiller's units
ext_dates = spy.index[spy.index > splice_month]
ext_nom_price = spy.loc[ext_dates] * scale

# extend nominal 10yr-avg earnings using corporate profits (CP) growth as a proxy - we don't have
# true S&P500 EPS post-2023, so approximate forward E growth using aggregate corporate profit growth.
cp = df["cp"] if "cp" in df.columns else None
if cp is None:
    cp_raw = pd.read_csv(os.path.join(BASE, "CP.csv"))
    cp_raw.columns = ["date", "value"]
    cp_raw["date"] = pd.to_datetime(cp_raw["date"])
    cp = cp_raw.set_index("date")["value"].resample("ME").last().reindex(df.index).ffill()

cp_growth = cp / cp.loc[:splice_month].iloc[-1]  # cumulative growth factor relative to splice month
last_nom_e10 = shiller.loc[splice_month, "nom_e10"]
ext_nom_e10 = last_nom_e10 * cp_growth.loc[ext_dates]

# CPI: convert to real terms using the SAME deflation convention Shiller used (real = nominal * CPI_ref/CPI_t).
# back out his implied CPI_ref from the splice point itself so the join is internally consistent.
our_cpi_at_splice = cpi.loc[splice_month] if splice_month in cpi.index else cpi.asof(splice_month)
shiller_real_at_splice = shiller.loc[splice_month, "real_price"]
implied_cpi_ref = shiller_real_at_splice / shiller_price_at_splice * our_cpi_at_splice

our_cpi_ext = cpi.loc[ext_dates]
ext_real_price = ext_nom_price * implied_cpi_ref / our_cpi_ext
ext_real_e10 = ext_nom_e10 * implied_cpi_ref / our_cpi_ext
ext_cape = ext_real_price / ext_real_e10

extended = pd.DataFrame({"real_price": ext_real_price, "real_e10": ext_real_e10, "cape": ext_cape})
print("\n===== 延伸出來的CAPE(2023-09之後，用企業利潤成長率推估盈餘) =====")
print(extended[["cape"]].round(1))

full_cape = pd.concat([shiller["cape"], extended["cape"]]).sort_index()
full_cape = full_cape[~full_cape.index.duplicated()]
# two known, real (not bugs) gaps: 2025-10 CPI delayed by the US government shutdown that month,
# and the very latest month where CPI simply hasn't been released yet at all - interpolate the
# isolated interior gap, and carry the last known value forward for the open-ended trailing one.
full_cape = full_cape.interpolate(limit=2).ffill()
full_cape.to_csv(os.path.join(BASE, "cape_full_extended.csv"), header=["cape"])
print("\n完整CAPE序列範圍:", full_cape.index.min(), "~", full_cape.index.max())
latest = full_cape.iloc[-1]
pctile = (full_cape < latest).mean() * 100
print(f"目前(最新, {full_cape.index[-1].strftime('%Y-%m')})CAPE: {latest:.1f}  歷史百分位: {pctile:.0f}%")
print("\n近12個月CAPE走勢:")
print(full_cape.tail(12).round(1).to_string())
