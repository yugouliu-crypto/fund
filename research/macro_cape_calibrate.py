import pandas as pd
import numpy as np
import os

BASE = os.path.dirname(os.path.abspath(__file__))
cape = pd.read_csv(os.path.join(BASE, "cape_full_extended.csv"), index_col=0, parse_dates=True)["cape"]

SPLICE = pd.Timestamp("2023-09-30")  # last real Shiller data point, ratio=1.0 here by definition
TRUE_POINT = cape.index[cape.index <= pd.Timestamp("2026-06-30")][-1]  # our latest estimated month
TRUE_VALUE = 41.58  # multpl.com, dated 2026-06-22

est_at_true_point = cape.loc[TRUE_POINT]
overall_ratio = TRUE_VALUE / est_at_true_point
print(f"估算值在{TRUE_POINT.date()}: {est_at_true_point:.2f}, 真實值(multpl.com): {TRUE_VALUE}, 比例: {overall_ratio:.4f}")

# linearly grow the correction from 1.0 at the splice point to `overall_ratio` at the true-value
# point (the gap vs. the CP-growth proxy likely accumulated gradually, not as a step change),
# leave everything before the splice point (Shiller's own real data) untouched.
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
print("\n校正後近12個月:")
print(calibrated.tail(12).round(1).to_string())
