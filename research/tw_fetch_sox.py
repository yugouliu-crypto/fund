"""Fetch the Philadelphia Semiconductor Index (^SOX) monthly history via Yahoo Finance's
chart API (no API key needed, server-to-server curl works fine - browser-side fetch would
hit Yahoo's CORS wall, same reasoning as the multpl.com CAPE scrape in the US model).
TSMC alone is roughly a third of TAIEX's market-cap weight, so SOX is a more structurally
relevant cross-market signal for Taiwan than the S&P 500 broad index."""
import subprocess
import json
import datetime
import pandas as pd
import os

BASE = os.path.dirname(os.path.abspath(__file__))
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

r = subprocess.run(["curl", "-s", "-A", UA, "--max-time", "20",
                     "https://query1.finance.yahoo.com/v8/finance/chart/%5ESOX?range=max&interval=1mo"],
                    capture_output=True)
d = json.loads(r.stdout.decode("utf-8"))
result = d["chart"]["result"][0]
ts = result["timestamp"]
closes = result["indicators"]["quote"][0]["close"]
rows = [{"date": datetime.datetime.fromtimestamp(t, datetime.timezone.utc).date(), "sox": c}
        for t, c in zip(ts, closes) if c is not None]
df = pd.DataFrame(rows)
df.to_csv(os.path.join(BASE, "tw_sox.csv"), index=False)
print(f"saved tw_sox.csv: {len(df)} rows, {df['date'].min()} to {df['date'].max()}")
