"""One-off patch: re-fetch the 14 months FMTQIK silently failed to return during the original
1990-2026 backfill (no retry logic existed in tw_fetch_data.py's first version), and merge
them into tw_taiex_daily.csv. Run once; safe to re-run (drops duplicates by date)."""
import subprocess
import json
import time
import pandas as pd
import os

BASE = os.path.dirname(os.path.abspath(__file__))
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

MISSING_MONTHS = ["1990-02", "1991-09", "1995-01", "1996-12", "1997-01", "1999-09",
                   "2013-08", "2013-10", "2014-02", "2014-10", "2018-01", "2019-10", "2021-03", "2022-11"]


def curl_json(url):
    r = subprocess.run(["curl", "-s", "-A", UA, "--max-time", "20", url], capture_output=True)
    try:
        return json.loads(r.stdout.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


def roc_to_ad(s):
    s = s.strip()
    y, m, d = s.split("/")
    return pd.Timestamp(year=int(y) + 1911, month=int(m), day=int(d))


new_rows = []
for ym in MISSING_MONTHS:
    date_str = ym.replace("-", "") + "01"
    data = None
    for attempt in range(3):
        data = curl_json(f"https://www.twse.com.tw/exchangeReport/FMTQIK?response=json&date={date_str}")
        if data and data.get("stat") == "OK":
            break
        time.sleep(1)
    if data and data.get("stat") == "OK":
        for row in data["data"]:
            try:
                new_rows.append({"date": roc_to_ad(row[0]), "taiex_close": float(row[4].replace(",", ""))})
            except (ValueError, IndexError):
                pass
        print(f"  {ym}: got {len(data['data'])} days")
    else:
        print(f"  {ym}: STILL FAILED ({data})")
    time.sleep(0.3)

existing = pd.read_csv(os.path.join(BASE, "tw_taiex_daily.csv"), parse_dates=["date"])
patched = pd.concat([existing, pd.DataFrame(new_rows)]).drop_duplicates(subset="date").sort_values("date")
patched.to_csv(os.path.join(BASE, "tw_taiex_daily.csv"), index=False)
print(f"saved, total rows now: {len(patched)}")
