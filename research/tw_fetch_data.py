"""
Fetch the Taiwan-side data sources confirmed feasible via direct curl (no headless browser
needed): TWSE's own TAIEX daily-close archive (FMTQIK, back to 1990-01-04 - covers the 1990
crash), TWSE's aggregate market margin-debt balance (MI_MARGN, back to 2001-01-01 only - TWSE
itself rejects earlier dates), and a handful of Taiwan series FRED happens to mirror (Taiwan
large-cap index, TWD/USD rate, export/import value, FX reserves). NDC's 景氣對策信號 lightscore
JSON API sits behind a Cloudflare + client-side device-detection redirect loop that plain curl
can't pass; CBC/DGBAS's CPI/M2/policy-rate databases are old ASP.NET postback forms, not REST
APIs - both are being collected manually by the user instead, not scraped here.
"""
import subprocess
import time
import json
import os
import re
import pandas as pd

BASE = os.path.dirname(os.path.abspath(__file__))
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"


def curl_json(url):
    r = subprocess.run(["curl", "-s", "-A", UA, "--max-time", "20", url], capture_output=True)
    try:
        return json.loads(r.stdout.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


def roc_to_ad(s):
    # TWSE returns dates like " 83/06/01" or "115/06/05" - ROC year + 1911 = AD year
    s = s.strip()
    y, m, d = s.split("/")
    return pd.Timestamp(year=int(y) + 1911, month=int(m), day=int(d))


# ---- 1. TAIEX daily close, 1990-01 through current month (one call per month) ----
print("+ fetching TAIEX (FMTQIK) month by month from 1990-01 ...")
taiex_rows = []
months = pd.date_range("1990-01-01", pd.Timestamp.today(), freq="MS")
for i, month_start in enumerate(months):
    date_str = month_start.strftime("%Y%m01")
    data = curl_json(f"https://www.twse.com.tw/exchangeReport/FMTQIK?response=json&date={date_str}")
    if data and data.get("stat") == "OK":
        for row in data["data"]:
            try:
                taiex_rows.append({"date": roc_to_ad(row[0]), "taiex_close": float(row[4].replace(",", ""))})
            except (ValueError, IndexError):
                pass
    if (i + 1) % 50 == 0:
        print(f"  ... {i + 1}/{len(months)} months")
    time.sleep(0.3)

taiex_df = pd.DataFrame(taiex_rows).drop_duplicates(subset="date").sort_values("date")
taiex_df.to_csv(os.path.join(BASE, "tw_taiex_daily.csv"), index=False)
print(f"  saved tw_taiex_daily.csv: {len(taiex_df)} rows, {taiex_df['date'].min()} to {taiex_df['date'].max()}")

# ---- 2. Aggregate market margin debt balance, 2001-01 through current month
#         (one trading day sampled per month - try day 5..14, first one that returns data) ----
print("+ fetching aggregate margin debt (MI_MARGN) one sample day per month from 2001-01 ...")
margin_rows = []
months2 = pd.date_range("2001-01-01", pd.Timestamp.today(), freq="MS")
for i, month_start in enumerate(months2):
    found = False
    for day in range(5, 15):
        try:
            d = month_start.replace(day=day)
        except ValueError:
            break
        data = curl_json(f"https://www.twse.com.tw/exchangeReport/MI_MARGN?response=json&date={d.strftime('%Y%m%d')}&selectType=ALL")
        time.sleep(0.3)
        if data and data.get("stat") == "OK":
            for table in data.get("tables", []):
                if "信用交易統計" in table.get("title", ""):
                    for row in table["data"]:
                        if row[0] == "融資金額(仟元)":
                            margin_rows.append({"date": d, "margin_balance_thousand_ntd": float(row[4].replace(",", ""))})
                            found = True
            if found:
                break
    if (i + 1) % 50 == 0:
        print(f"  ... {i + 1}/{len(months2)} months")

margin_df = pd.DataFrame(margin_rows).drop_duplicates(subset="date").sort_values("date")
margin_df.to_csv(os.path.join(BASE, "tw_margin_debt.csv"), index=False)
print(f"  saved tw_margin_debt.csv: {len(margin_df)} rows, {margin_df['date'].min()} to {margin_df['date'].max()}")

# ---- 3. FRED's Taiwan series ----
FRED_TW = {
    "NASDAQNQTWLC": "tw_nasdaq_largecap.csv",
    "EXTAUS": "tw_fx_usd.csv",
    "VALEXPTWM052N": "tw_exports.csv",
    "VALIMPTWM052N": "tw_imports.csv",
    "TRESEGTWM194N": "tw_fx_reserves.csv",
}
for series, fname in FRED_TW.items():
    print(f"+ fetching FRED:{series}")
    r = subprocess.run(["curl", "-s", f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}"],
                        capture_output=True)
    text = r.stdout.decode("utf-8", errors="replace")
    if text.startswith("observation_date") and len(text) > 50:
        with open(os.path.join(BASE, fname), "w", encoding="utf-8") as f:
            f.write(text)
        print(f"  saved {fname} ({len(text.splitlines())} lines)")
    else:
        print(f"  WARNING: unexpected response for {series}, skipped")

print("\n=== done ===")
