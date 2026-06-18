import csv, os
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))

def parse_date(s):
    s = s.strip()
    return datetime.strptime(s, "%Y/%m/%d").date() if '/' in s else datetime.strptime(s, "%Y%m%d").date()

def load_div(fn):
    rows=[]
    with open(os.path.join(BASE, fn), encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows.append({"basis": parse_date(row["basis"]), "exdiv": parse_date(row["exdiv"])})
    rows.sort(key=lambda x: x["basis"])
    return rows

JFZN3 = load_div("jfzn3_div.csv")
TLZN0 = load_div("tlzn0_div.csv")
ALBT8 = load_div("albt8_div.csv")

def gaps(out_list, in_list, label):
    diffs=[]
    for o in out_list:
        nxt = [i for i in in_list if i["basis"] >= o["exdiv"]]
        if not nxt: continue
        d = (nxt[0]["basis"] - o["exdiv"]).days
        diffs.append(d)
    print(f"{label}: 最小{min(diffs)}天 / 中位數{sorted(diffs)[len(diffs)//2]}天 / 最大{max(diffs)}天  (樣本{len(diffs)}筆)")

gaps(JFZN3, TLZN0, "JFZN3除息 -> TLZN0下次基準日")
gaps(TLZN0, ALBT8, "TLZN0除息 -> ALBT8下次基準日")
gaps(ALBT8, JFZN3, "ALBT8除息 -> JFZN3下次基準日")
