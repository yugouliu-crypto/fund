import csv
import os
from datetime import datetime, timedelta

BASE = os.path.dirname(os.path.abspath(__file__))
FX = 31.5

def parse_date(s):
    s = s.strip()
    if '/' in s:
        return datetime.strptime(s, "%Y/%m/%d").date()
    return datetime.strptime(s, "%Y%m%d").date()

def load_nav(fn):
    rows = []
    with open(f"{BASE}\\{fn}", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            rows.append((parse_date(row["date"]), float(row["nav"])))
    rows.sort(key=lambda x: x[0])
    return rows

def load_div(fn):
    rows = []
    with open(f"{BASE}\\{fn}", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            rows.append({
                "basis": parse_date(row["basis"]),
                "exdiv": parse_date(row["exdiv"]),
                "amount": float(row["amount"]),
            })
    rows.sort(key=lambda x: x["basis"])
    return rows

FUNDS = {
    "JFZN3": {"name": "摩根多重收益", "nav": load_nav("jfzn3_nav.csv"), "div": load_div("jfzn3_div.csv")},
    "TLZN0": {"name": "安聯全球", "nav": load_nav("tlzn0_nav.csv"), "div": load_div("tlzn0_div.csv")},
    "ALBT8": {"name": "聯博美國成長", "nav": load_nav("albt8_nav.csv"), "div": load_div("albt8_div.csv")},
}

def nav_on_or_after(navlist, d, max_search=10):
    for i, (dt, v) in enumerate(navlist):
        if dt >= d:
            return i, dt, v
    return None, None, None

def nav_at_index(navlist, idx):
    if idx is None or idx >= len(navlist):
        return None, None
    return navlist[idx]

# ---------- Part 1: ex-dividend +3 trading day NAV performance, last 2 years ----------
print("="*100)
print("Part 1: 除息日後3個交易日淨值表現 (2024/06/18 ~ 2026/06/18)")
print("="*100)

WINDOW_START = datetime(2024,6,18).date()

for code, f in FUNDS.items():
    print(f"\n--- {f['name']} ({code}) ---")
    print(f"{'基準日':<12}{'除息日':<12}{'配息金額':>10}  {'除息日NAV':>10}  {'除息+3日':<12}{'+3日NAV':>10}  {'漲跌%':>8}")
    for d in f["div"]:
        if d["basis"] < WINDOW_START:
            continue
        idx, exdate, exnav = nav_on_or_after(f["nav"], d["exdiv"])
        if idx is None:
            print(f"{d['basis']}  {d['exdiv']}  {d['amount']:>10}  NAV資料缺")
            continue
        date3, nav3 = nav_at_index(f["nav"], idx+3)
        if nav3 is None:
            print(f"{d['basis']}  {d['exdiv']}  {d['amount']:>10}  {exnav:>10.4f}  (3日後資料不足)")
            continue
        chg = (nav3/exnav - 1)*100
        print(f"{str(d['basis']):<12}{str(d['exdiv']):<12}{d['amount']:>10.4f}  {exnav:>10.4f}  {str(date3):<12}{nav3:>10.4f}  {chg:>7.2f}%")

# ---------- Part 2: rotation simulation ----------
print("\n"+"="*100)
print("Part 2: 循環轉換模擬 (JFZN3 -> TLZN0 -> ALBT8 -> JFZN3 ...)")
print("="*100)

ORDER = ["JFZN3", "TLZN0", "ALBT8"]

# find first date where ALL funds have nav data (limiting factor = ALBT8)
start_date = max(f["nav"][0][0] for f in FUNDS.values())
print(f"\n模擬起始日 (受限於聯博AP級別淨值資料起點): {start_date}")

principal_twd = 1_000_000
principal_usd = principal_twd / FX
print(f"起始本金: TWD {principal_twd:,.0f} / 匯率{FX} = USD {principal_usd:,.2f}")

cur_fund = "JFZN3"
idx0, d0, nav0 = nav_on_or_after(FUNDS[cur_fund]["nav"], start_date)
units = principal_usd / nav0
entry_date = d0
print(f"\n[買入] {entry_date}  買進 {FUNDS[cur_fund]['name']}({cur_fund})  NAV={nav0:.4f}  單位數={units:.4f}")

total_div_usd = {k:0.0 for k in FUNDS}
log = []
cycle = 0
END_DATE = datetime(2026,6,18).date()

while True:
    fund = FUNDS[cur_fund]
    # find next dividend event with basis date >= entry_date
    next_div = None
    for d in fund["div"]:
        if d["basis"] >= entry_date:
            next_div = d
            break
    if next_div is None:
        break
    if next_div["exdiv"] > END_DATE:
        break

    div_per_unit = next_div["amount"]
    div_usd = units * div_per_unit
    div_twd = div_usd * FX
    total_div_usd[cur_fund] += div_usd

    # conversion happens at exdiv date NAV (old fund), into next fund NAV same date
    idx_out, date_out, nav_out = nav_on_or_after(fund["nav"], next_div["exdiv"])
    usd_value = units * nav_out

    next_idx = (ORDER.index(cur_fund)+1) % 3
    next_fund_code = ORDER[next_idx]
    idx_in, date_in, nav_in = nav_on_or_after(FUNDS[next_fund_code]["nav"], next_div["exdiv"])
    new_units = usd_value / nav_in

    log.append({
        "cycle": cycle,
        "fund": cur_fund,
        "fund_name": fund["name"],
        "entry_date": entry_date,
        "basis": next_div["basis"],
        "exdiv": next_div["exdiv"],
        "div_per_unit": div_per_unit,
        "units_held": units,
        "div_usd": div_usd,
        "div_twd": div_twd,
        "convert_date": date_out,
        "nav_out": nav_out,
        "usd_value": usd_value,
        "next_fund": next_fund_code,
        "nav_in": nav_in,
        "new_units": new_units,
    })

    cur_fund = next_fund_code
    units = new_units
    entry_date = date_in
    cycle += 1

print(f"\n共完成 {cycle} 次轉換\n")
print(f"{'#':<4}{'持有基金':<14}{'轉入日':<12}{'基準日':<12}{'除息日':<12}{'配息/單位':>10}{'持有單位數':>12}{'配息(USD)':>12}{'配息(TWD)':>12}{'轉換NAV':>9}{'轉入下一基金':<14}{'新NAV':>9}{'新單位數':>12}")
for r in log:
    print(f"{r['cycle']:<4}{r['fund_name']:<14}{str(r['entry_date']):<12}{str(r['basis']):<12}{str(r['exdiv']):<12}{r['div_per_unit']:>10.5f}{r['units_held']:>12.3f}{r['div_usd']:>12.2f}{r['div_twd']:>12.0f}{r['nav_out']:>9.4f}{FUNDS[r['next_fund']]['name']:<14}{r['nav_in']:>9.4f}{r['new_units']:>12.3f}")

print(f"\n最後持有: {FUNDS[cur_fund]['name']} ({cur_fund})，自 {entry_date} 起持有 {units:.4f} 單位，尚未到下次基準日(資料範圍內)")
idx_last, date_last, nav_last = nav_on_or_after(FUNDS[cur_fund]["nav"], END_DATE)
if date_last is None:
    date_last, nav_last = FUNDS[cur_fund]["nav"][-1]
final_value_usd = units * nav_last
final_value_twd = final_value_usd * FX
print(f"以資料最後一日 {date_last} NAV={nav_last:.4f} 計算，市值 = USD {final_value_usd:,.2f} = TWD {final_value_twd:,.0f}")

with open(f"{BASE}\\rotation_log.csv", "w", encoding="utf-8-sig", newline="") as fcsv:
    w = csv.writer(fcsv)
    w.writerow(["序號","持有基金","轉入日","基準日","除息日","配息每單位(USD)","持有單位數","配息(USD)","配息(TWD)","轉換日NAV","轉入下一基金","新基金NAV","新單位數"])
    for r in log:
        w.writerow([r["cycle"], r["fund_name"], r["entry_date"], r["basis"], r["exdiv"], r["div_per_unit"], round(r["units_held"],4), round(r["div_usd"],2), round(r["div_twd"],0), r["nav_out"], FUNDS[r["next_fund"]]["name"], r["nav_in"], round(r["new_units"],4)])

with open(f"{BASE}\\ex_div_3day_nav.csv", "w", encoding="utf-8-sig", newline="") as fcsv:
    w = csv.writer(fcsv)
    w.writerow(["基金","基準日","除息日","配息金額","除息日NAV","除息+3交易日","+3日NAV","漲跌%"])
    for code, f in FUNDS.items():
        for d in f["div"]:
            if d["basis"] < WINDOW_START:
                continue
            idx, exdate, exnav = nav_on_or_after(f["nav"], d["exdiv"])
            if idx is None:
                continue
            date3, nav3 = nav_at_index(f["nav"], idx+3)
            if nav3 is None:
                w.writerow([f["name"], d["basis"], d["exdiv"], d["amount"], exnav, "", "", ""])
                continue
            chg = round((nav3/exnav - 1)*100, 2)
            w.writerow([f["name"], d["basis"], d["exdiv"], d["amount"], exnav, date3, nav3, chg])

print("\n--- 各基金累計配息總額 ---")
grand_total_usd = 0
for k in FUNDS:
    grand_total_usd += total_div_usd[k]
    print(f"{FUNDS[k]['name']}({k}): USD {total_div_usd[k]:,.2f} = TWD {total_div_usd[k]*FX:,.0f}")
print(f"配息總計: USD {grand_total_usd:,.2f} = TWD {grand_total_usd*FX:,.0f}")

print(f"\n本金期末市值 + 累計配息(現金) = TWD {final_value_twd:,.0f} + TWD {grand_total_usd*FX:,.0f} = TWD {final_value_twd+grand_total_usd*FX:,.0f}")
total_return = (final_value_twd+grand_total_usd*FX)/principal_twd - 1
print(f"總報酬率(未扣手續費/稅): {total_return*100:.2f}%  期間: {start_date} ~ {date_last}")
