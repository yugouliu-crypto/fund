import pandas as pd
import numpy as np
import os
import re
import subprocess
import tempfile

BASE = os.path.dirname(os.path.abspath(__file__))

def fetch_multpl_cape():
    """live Shiller PE reading from multpl.com's page meta description
    ("Current Shiller PE Ratio is 41.58, a change of ..."), which is far more reliable to
    regex out than the rendered page body (full of unrelated numbers, including SVG path data
    that looks numeric). Returns None on any failure - caller must treat that as "skip
    calibration this run, keep whatever ratio was already baked in" rather than crash."""
    with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        r = subprocess.run(["curl", "-sL", "-o", tmp_path, "https://www.multpl.com/shiller-pe", "--max-time", "20"])
        if r.returncode != 0:
            return None
        with open(tmp_path, encoding="utf-8", errors="ignore") as f:
            content = f.read()
        m = re.search(r"Current Shiller PE Ratio is ([0-9.]+)", content)
        return float(m.group(1)) if m else None
    except Exception as e:
        print(f"multpl.com fetch failed: {e}")
        return None
    finally:
        os.path.exists(tmp_path) and os.remove(tmp_path)

if __name__ == "__main__":
    cape = pd.read_csv(os.path.join(BASE, "cape_full_extended.csv"), index_col=0, parse_dates=True)["cape"]

    SPLICE = pd.Timestamp("2023-09-30")  # last real Shiller data point, ratio=1.0 here by definition
    TRUE_POINT = cape.index[-1]  # our latest estimated month

    true_value = fetch_multpl_cape()
    if true_value is None:
        print("無法取得multpl.com即時數值，保留原本的CP推估值，不做校正")
    else:
        est_at_true_point = cape.loc[TRUE_POINT]
        overall_ratio = true_value / est_at_true_point
        print(f"估算值在{TRUE_POINT.date()}: {est_at_true_point:.2f}, 即時真實值(multpl.com): {true_value}, 比例: {overall_ratio:.4f}")

        # linearly grow the correction from 1.0 at the splice point to `overall_ratio` at the
        # true-value point (the gap vs the CP-growth proxy likely accumulates gradually, not as
        # a step change); leave everything at/before the splice point (Shiller's own real data)
        # untouched.
        total_days = (TRUE_POINT - SPLICE).days
        calibrated = cape.copy()
        mask = (cape.index > SPLICE) & (cape.index <= TRUE_POINT)
        for d in cape.index[mask]:
            w = (d - SPLICE).days / total_days
            factor = 1 - w * (1 - overall_ratio)
            calibrated.loc[d] = cape.loc[d] * factor

        calibrated.to_csv(os.path.join(BASE, "cape_full_extended.csv"), header=["cape"])
        latest = calibrated.iloc[-1]
        pctile = (calibrated < latest).mean() * 100
        print(f"\n校正後目前CAPE: {latest:.1f}  歷史百分位: {pctile:.0f}%")
