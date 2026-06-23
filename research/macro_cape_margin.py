import pandas as pd
import numpy as np
import os

BASE = os.path.dirname(os.path.abspath(__file__))

# ---- Shiller CAPE (1871-2023) ----
shiller = pd.read_excel(os.path.join(BASE, "shiller_ie_data.xls"), sheet_name="Data", skiprows=7)
shiller = shiller.dropna(subset=["Date"])
shiller = shiller[shiller["Date"].apply(lambda x: isinstance(x, (int, float)))]
shiller["date"] = pd.to_datetime(shiller["Date"].astype(str).str.replace(".", "-", regex=False) + "-01", format="%Y-%m-%d", errors="coerce")
# Shiller encodes October as "...1" not "...10" (e.g. 2000.1 = Oct 2000, not Jan); fix via the
# fractional part: round(frac*12) gives the month directly since values are YYYY.MM with Jan="01"...
# actually Shiller's own convention: 2000.10 = October 2000 (not 1.0=Jan,Oct=10 ambiguity) - validate below.
shiller["year"] = shiller["Date"].apply(lambda x: int(x))
shiller["month_raw"] = shiller["Date"].apply(lambda x: round((x - int(x)) * 100))
shiller["month"] = shiller["month_raw"].replace(0, 1)
shiller["date"] = pd.to_datetime(dict(year=shiller["year"], month=shiller["month"], day=1))
shiller = shiller.set_index("date")[["P", "CAPE"]].rename(columns={"P": "sp500_shiller", "CAPE": "cape"})
shiller["cape"] = pd.to_numeric(shiller["cape"], errors="coerce")
shiller = shiller.dropna()
print("Shiller CAPE range:", shiller.index.min(), "~", shiller.index.max())
print(shiller.tail(3))

# ---- FINRA margin debt (1997-2026) ----
margin = pd.read_excel(os.path.join(BASE, "finra_margin.xlsx"), sheet_name="Customer Margin Balances")
margin.columns = ["yearmonth", "debit_balance", "free_credit_cash", "free_credit_margin"]
margin["date"] = pd.to_datetime(margin["yearmonth"] + "-01")
margin = margin.set_index("date")["debit_balance"].sort_index().resample("ME").last()
print("\nFINRA margin debt range:", margin.index.min(), "~", margin.index.max())

shiller.to_csv(os.path.join(BASE, "shiller_cape_clean.csv"))
margin.to_csv(os.path.join(BASE, "finra_margin_clean.csv"))

# ---- merge with our existing macro_final.csv (has spy + the 7 events context) ----
df = pd.read_csv(os.path.join(BASE, "macro_final.csv"), index_col=0, parse_dates=True)
df["cape"] = shiller["cape"].resample("ME").last().reindex(df.index)
df["margin_debt"] = margin.reindex(df.index)
df["margin_yoy"] = df["margin_debt"].pct_change(12) * 100

events = {
    "1998 LTCM": "1998-06", "2000 dot-com": "2000-08", "2008 GFC": "2007-10",
    "2016 mini修正": "2015-05", "2018 Q4賣壓": "2018-09", "2020 疫情": "2019-12",
    "2022 升息熊市": "2021-12",
}
print("\n===== 每次危機高點時，CAPE是多少(及當時百分位) =====")
for name, peak in events.items():
    peak_d = pd.Timestamp(peak + "-01") + pd.offsets.MonthEnd(0)
    cape_at_peak = df.loc[:peak_d, "cape"].dropna()
    if len(cape_at_peak) == 0:
        continue
    val = cape_at_peak.iloc[-1]
    pctile = (cape_at_peak < val).mean() * 100
    print(f"{name} ({peak}): CAPE={val:.1f}  (歷史百分位={pctile:.0f}%)")

print("\n===== 每次危機高點時，融資餘額年增率是多少 =====")
for name, peak in events.items():
    peak_d = pd.Timestamp(peak + "-01") + pd.offsets.MonthEnd(0)
    val = df.loc[:peak_d, "margin_yoy"].dropna()
    if len(val) == 0:
        print(f"{name} ({peak}): 無資料(早於1998年margin debt資料起點)")
        continue
    print(f"{name} ({peak}): 融資餘額年增率={val.iloc[-1]:.1f}%")
