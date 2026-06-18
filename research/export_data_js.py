import csv, json, os
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "..", "data.js")

def parse_date(s):
    s = s.strip()
    if '/' in s:
        d = datetime.strptime(s, "%Y/%m/%d").date()
    else:
        d = datetime.strptime(s, "%Y%m%d").date()
    return d.isoformat()

def load_nav(fn):
    rows = []
    with open(f"{BASE}\\{fn}", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows.append([parse_date(row["date"]), float(row["nav"])])
    rows.sort(key=lambda x: x[0])
    return rows

def load_div(fn):
    rows = []
    with open(f"{BASE}\\{fn}", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows.append({"basis": parse_date(row["basis"]), "exdiv": parse_date(row["exdiv"]), "amount": float(row["amount"])})
    rows.sort(key=lambda x: x["basis"])
    return rows

data = {
    "FUNDS": {
        "JFZN3": {"name": "摩根多重收益", "fullName": "摩根投資基金-多重收益基金A股(美元對沖)(穩定月配)", "currency": "USD",
                  "nav": load_nav("jfzn3_nav.csv"), "div": load_div("jfzn3_div.csv")},
        "TLZN0": {"name": "安聯全球", "fullName": "安聯全球永續發展基金-AMg穩定月收總收益類股(美元)", "currency": "USD",
                  "nav": load_nav("tlzn0_nav.csv"), "div": load_div("tlzn0_div.csv")},
        "ALBT8": {"name": "聯博美國成長", "fullName": "聯博-美國成長基金AP總報酬月配美元", "currency": "USD",
                  "nav": load_nav("albt8_nav.csv"), "div": load_div("albt8_div.csv")},
    },
    "TECH": {"name": "安聯台灣科技", "fullName": "安聯台灣科技基金", "currency": "TWD", "nav": load_nav("acdd04_nav.csv")},
    "ORDER": ["JFZN3", "TLZN0", "ALBT8"],
}

with open(OUT, "w", encoding="utf-8") as f:
    f.write("const FUND_DATA = ")
    json.dump(data, f, ensure_ascii=False)
    f.write(";\n")

print("written", OUT)
