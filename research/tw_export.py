"""
Export the Taiwan-side panel to tw_data.js for a dashboard page, mirroring macro_data.js's
shape so tw_engine.js/tw_dashboard.js can reuse the exact same z-score/drawdown functions as
the US model. Only 6 derived indicators exist so far (margin debt, exports, imports, TWD/USD,
FX reserves, trade balance) - no CPI/M2/景氣燈號/PE yet (user is collecting those manually),
and no CAPE-equivalent valuation gate yet either. The dashboard text must say so plainly:
this is an early, partial version, not the same maturity as the 17-indicator US model.
"""
import pandas as pd
import numpy as np
import json
import os

BASE = os.path.dirname(os.path.abspath(__file__))
df = pd.read_csv(os.path.join(BASE, "tw_merged.csv"), index_col=0, parse_dates=True)


def series_to_pairs(s):
    s = s.dropna()
    return [[d.strftime("%Y-%m"), round(float(v), 4)] for d, v in s.items()]


RAW_COLS = {
    "margin_yoy": "margin_yoy", "exports_yoy": "exports_yoy", "imports_yoy": "imports_yoy",
    "fx_usd_yoy": "fx_usd_yoy", "fx_reserves_yoy": "fx_reserves_yoy",
    "trade_balance_yoy_chg": "trade_balance_yoy_chg",
}
indicators = {key: series_to_pairs(df[col]) for key, col in RAW_COLS.items()}

taiex_d = pd.read_csv(os.path.join(BASE, "tw_taiex_daily.csv"), parse_dates=["date"]).set_index("date")["taiex_close"]
taiex_m = taiex_d.resample("ME").last()
taiex_pairs = series_to_pairs(taiex_m)

sox = pd.read_csv(os.path.join(BASE, "tw_sox.csv"), parse_dates=["date"]).set_index("date")["sox"].resample("ME").last()
sox_pairs = series_to_pairs(sox)

# tier=1 flat for all six - not enough cross-indicator lead-time evidence yet to justify the
# US model's 3-tier weighting scheme, so the composite score here is an unweighted anomaly count.
TIERS = {
    "margin_yoy": {"tier": 1, "direction": 1, "label": "台股融資餘額年增率異常"},
    "exports_yoy": {"tier": 1, "direction": -1, "label": "出口值年增率轉弱"},
    "imports_yoy": {"tier": 1, "direction": -1, "label": "進口值年增率轉弱"},
    "fx_usd_yoy": {"tier": 1, "direction": 1, "label": "台幣兌美元年貶值率"},
    "fx_reserves_yoy": {"tier": 1, "direction": -1, "label": "外匯存底年增率轉弱"},
    "trade_balance_yoy_chg": {"tier": 1, "direction": -1, "label": "貿易餘額年變化轉弱"},
}

EVENTS = [
    {"label": "1990 泡沫破裂", "date": "1990-01"},
    {"label": "1997-98 亞洲金融風暴", "date": "1997-08"},
    {"label": "2000-01 網路泡沫", "date": "2000-02"},
    {"label": "2008 金融海嘯", "date": "2008-05"},
    {"label": "2011 歐債危機", "date": "2011-06"},
    {"label": "2015-16 中國放緩", "date": "2015-04"},
    {"label": "2018 Q4 賣壓", "date": "2018-06"},
    {"label": "2020 疫情", "date": "2020-01"},
    {"label": "2022 升息熊市", "date": "2022-01"},
]

out = {
    "indicators": indicators, "taiex": taiex_pairs, "sox": sox_pairs,
    "events": EVENTS, "tiers": TIERS, "rollWindowMonths": 60,
}
out_path = os.path.join(BASE, "..", "tw_data.js")
with open(out_path, "w", encoding="utf-8") as f:
    f.write("const TW_DATA = ")
    json.dump(out, f, ensure_ascii=False)
    f.write(";\n")
print("written", out_path)
print("indicators:", {k: len(v) for k, v in indicators.items()})
print("taiex:", len(taiex_pairs), "sox:", len(sox_pairs))
