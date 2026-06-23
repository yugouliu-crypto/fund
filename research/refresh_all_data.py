"""
One-shot refresh of every raw data source the macro dashboard depends on (21 FRED series,
Shiller's CAPE workbook, FINRA margin debt, plus a live multpl.com check to calibrate the
post-Shiller CAPE estimate), then re-exports macro_data.js. Designed to be run unattended
(e.g. by the weekly GitHub Actions workflow) - every step is best-effort: a single failed
fetch (a renamed FRED series, a flaky host) should not stop the rest of the pipeline, since
most of the upstream value is in the OTHER ~20 series still refreshing successfully. Logs
failures clearly instead of silently swallowing them. If the multpl.com check itself fails,
macro_cape_calibrate.py just skips calibration for that run and keeps the raw CP-proxy
estimate - it never blocks the rest of the pipeline.
"""
import subprocess
import sys
import os
import shutil
import tempfile
import time

BASE = os.path.dirname(os.path.abspath(__file__))

FRED_SERIES = [
    "DGS10", "DGS2", "UNRATE", "BAMLH0A0HYM2", "BAA10Y", "CPIAUCSL", "M2SL", "VIXCLS",
    "DCOILWTICO", "PCOPPUSDM", "HOUST", "PERMIT", "MORTGAGE30US", "CSUSHPISA", "BOPGSTB",
    "NETEXP", "ICSA", "NEWORDER", "NFCI", "DRTSCILM", "CP",
]

failures = []

def fetch(url, dest, min_bytes, retries=3):
    """download to a temp file, only replace `dest` once the result passes a size sanity
    check - a truncated/flaky download (seen in practice with Yale's old server) must never
    overwrite a previously-good file with garbage."""
    for attempt in range(1, retries + 1):
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp_path = tmp.name
        r = subprocess.run(["curl", "-s", "-o", tmp_path, "-w", "%{http_code}", url, "--max-time", "30"],
                            capture_output=True, text=True)
        code = r.stdout.strip()
        size = os.path.getsize(tmp_path) if os.path.exists(tmp_path) else 0
        if code == "200" and size >= min_bytes:
            shutil.move(tmp_path, dest)
            return True
        os.path.exists(tmp_path) and os.remove(tmp_path)
        print(f"  attempt {attempt}/{retries} failed (http={code}, size={size}, need>={min_bytes})")
        if attempt < retries:
            time.sleep(3)
    return False

for series in FRED_SERIES:
    print(f"+ fetching FRED:{series}")
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}"
    ok = fetch(url, os.path.join(BASE, f"{series}.csv"), min_bytes=50)
    if not ok:
        failures.append(f"FRED:{series}")

print("+ fetching Shiller CAPE")
ok = fetch("http://www.econ.yale.edu/~shiller/data/ie_data.xls",
           os.path.join(BASE, "shiller_ie_data.xls"), min_bytes=1_000_000)
if not ok:
    failures.append("Shiller CAPE")

print("+ fetching FINRA margin debt")
ok = fetch("https://www.finra.org/sites/default/files/2021-03/margin-statistics.xlsx",
           os.path.join(BASE, "finra_margin.xlsx"), min_bytes=10_000)
if not ok:
    failures.append("FINRA margin")

if failures:
    print("\n=== WARNING: the following fetches failed after retries, kept the previous file ===")
    for f in failures:
        print(" -", f)

# re-run the processing pipeline in dependency order: raw FRED CSVs -> macro_merged.csv ->
# macro_with_anomaly.csv -> macro_final.csv -> shiller/finra cleaned + CAPE CP-proxy estimate
# -> live-calibrate that estimate against multpl.com's published reading -> export macro_data.js.
for script in ["macro_model.py", "macro_anomaly.py", "macro_cross_event_v3.py",
               "macro_cape_margin.py", "macro_cape_extend.py", "macro_cape_calibrate.py",
               "export_macro_js_v2.py"]:
    print(f"+ running {script}")
    r = subprocess.run([sys.executable, script], cwd=BASE)
    if r.returncode != 0:
        print(f"FATAL: {script} failed, aborting")
        sys.exit(1)

print("\n=== refresh complete ===")
if failures:
    print(f"({len(failures)} source(s) failed to update this run, kept stale data for those - see warnings above)")
