import pandas as pd
import numpy as np
import json
import os

BASE = os.path.dirname(os.path.abspath(__file__))
df = pd.read_csv(os.path.join(BASE, "macro_final.csv"), index_col=0, parse_dates=True)

# raw monthly series we want to expose to the front end (already merged at month-end).
# cpi_yoy is deliberately NOT here - it's the confirmation-layer target, exported separately
# below as its own top-level field, and must not appear in MACRO_DATA.tiers either.
RAW_COLS = {
    "yield_spread": "yield_spread", "sahm": "sahm", "m2_yoy": "m2_yoy",
    "vix": "vix", "baa10y": "baa10y", "oil_yoy": "oil_yoy", "copper_yoy": "copper_yoy",
    "houst_yoy": "houst_yoy", "permit_yoy": "permit_yoy", "mortgage_chg_12m": "mortgage_chg_12m",
    "caseshiller_yoy": "caseshiller_yoy", "trade_balance_yoy_chg": "trade_balance_yoy_chg",
    "icsa_yoy": "icsa_yoy", "neworder_yoy": "neworder_yoy", "nfci": "nfci", "sloos": "sloos",
}

def series_to_pairs(s):
    s = s.dropna()
    return [[d.strftime("%Y-%m"), round(float(v), 4)] for d, v in s.items()]

indicators = {}
for key, col in RAW_COLS.items():
    indicators[key] = series_to_pairs(df[col])

spy = series_to_pairs(df["spy"])

acdd04_df = pd.read_csv(os.path.join(BASE, "acdd04_monthly_since_inception.csv"))
acdd04_df["date"] = pd.to_datetime(acdd04_df["date"])
acdd04_s = acdd04_df.set_index("date")["nav"].resample("ME").last()
acdd04 = series_to_pairs(acdd04_s)

# known historical crisis peak dates, for marking on the chart
EVENTS = [
    {"label": "1998 LTCM危機", "date": "1998-06"},
    {"label": "2000 網路泡沫", "date": "2000-08"},
    {"label": "2008 金融海嘯", "date": "2007-10"},
    {"label": "2016 中國放緩修正", "date": "2015-05"},
    {"label": "2018 Q4賣壓", "date": "2018-09"},
    {"label": "2020 疫情", "date": "2019-12"},
    {"label": "2022 升息熊市", "date": "2021-12"},
]

# indicator metadata: which of the 3 leading tiers each belongs to, and direction (+1 means
# "higher value = more stress", matching the z-score direction convention used throughout)
TIERS = {
    "caseshiller_yoy": {"tier": 1, "direction": -1, "label": "房價(Case-Shiller)年增率轉負"},
    "mortgage_chg_12m": {"tier": 1, "direction": 1, "label": "房貸利率12月內急升"},
    "houst_yoy": {"tier": 1, "direction": -1, "label": "新屋開工年減"},
    "permit_yoy": {"tier": 1, "direction": -1, "label": "建照年減"},
    "nfci": {"tier": 1, "direction": 1, "label": "NFCI全國金融狀況指數"},
    "neworder_yoy": {"tier": 1, "direction": -1, "label": "耐久財新訂單年減(PMI替代)"},
    "trade_balance_yoy_chg": {"tier": 1, "direction": -1, "label": "貿易餘額急速擴大"},
    "sloos": {"tier": 2, "direction": 1, "label": "銀行緊縮放款標準"},
    "vix": {"tier": 2, "direction": 1, "label": "VIX恐慌指數"},
    "m2_yoy": {"tier": 2, "direction": 1, "label": "M2貨幣供給年增率異常"},
    "sahm": {"tier": 2, "direction": 1, "label": "Sahm Rule失業率訊號"},
    "icsa_yoy": {"tier": 2, "direction": 1, "label": "初領失業金年增率"},
    "oil_yoy": {"tier": 3, "direction": 1, "label": "油價年增率飆升"},
    "yield_spread": {"tier": 3, "direction": -1, "label": "殖利率倒掛(10Y-2Y)"},
    "copper_yoy": {"tier": 0, "direction": -1, "label": "銅價年增率(參考用,歷史上沒驗證出預測力)"},
    "baa10y": {"tier": 0, "direction": 1, "label": "信用價差(Baa-10Y,參考用)"},
}
CPI_META = {"direction": 1, "label": "CPI年增率(確認層,不算入分級分數)"}

out = {
    "indicators": indicators,
    "cpi_yoy": series_to_pairs(df["cpi_yoy"]),
    "spy": spy,
    "acdd04": acdd04,
    "events": EVENTS,
    "tiers": TIERS,
    "cpiMeta": CPI_META,
    "rollWindowMonths": 60,
}

out_path = os.path.join(BASE, "..", "macro_data.js")
with open(out_path, "w", encoding="utf-8") as f:
    f.write("const MACRO_DATA = ")
    json.dump(out, f, ensure_ascii=False)
    f.write(";\n")

print("written", out_path)
print("indicators:", list(indicators.keys()))
print("spy rows:", len(spy), "acdd04 rows:", len(acdd04))
