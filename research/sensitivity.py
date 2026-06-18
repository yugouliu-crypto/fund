import csv, math, os
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
        for row in csv.DictReader(f):
            rows.append((parse_date(row["date"]), float(row["nav"])))
    rows.sort(key=lambda x: x[0])
    return rows

def load_div(fn):
    rows = []
    with open(f"{BASE}\\{fn}", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows.append({"basis": parse_date(row["basis"]), "exdiv": parse_date(row["exdiv"]), "amount": float(row["amount"])})
    rows.sort(key=lambda x: x["basis"])
    return rows

FUNDS = {
    "JFZN3": {"name": "摩根多重收益", "nav": load_nav("jfzn3_nav.csv"), "div": load_div("jfzn3_div.csv")},
    "TLZN0": {"name": "安聯全球", "nav": load_nav("tlzn0_nav.csv"), "div": load_div("tlzn0_div.csv")},
    "ALBT8": {"name": "聯博美國成長", "nav": load_nav("albt8_nav.csv"), "div": load_div("albt8_div.csv")},
}
TECH = {"name": "安聯台灣科技", "nav": load_nav("acdd04_nav.csv")}

ORDER = ["JFZN3", "TLZN0", "ALBT8"]

def nav_on_or_after(navlist, d):
    for i, (dt, v) in enumerate(navlist):
        if dt >= d:
            return i, dt, v
    return None, None, None

START_DATE = max(f["nav"][0][0] for f in FUNDS.values())
END_DATE = datetime(2026,6,18).date()
PRINCIPAL_TWD = 1_000_000
PRINCIPAL_USD = PRINCIPAL_TWD/FX

def simulate(switch_delay_days=0, redirect_pct=0.0, settlement_days=0):
    """
    switch_delay_days: 除息日後再等幾天才執行轉換(模擬人工延遲/排隊)
    settlement_days: 贖回款項日數(模擬保單契約贖回到位天數)，影響新基金買入日(在 switch_delay 基礎上再延後)
    redirect_pct: 每筆配息中轉出到安聯科技的比例 (0~1)，留在身上的(1-redirect_pct)算現金
    回傳: dict 含期末本金市值、配息總額(留存現金)、安聯科技基金期末市值、總計、是否有任一腿來不及(漏配息)
    """
    cur_fund = "JFZN3"
    idx0, d0, nav0 = nav_on_or_after(FUNDS[cur_fund]["nav"], START_DATE)
    units = PRINCIPAL_USD/nav0
    entry_date = d0
    tech_units = 0.0
    total_cash_usd = 0.0
    missed = 0
    cycles = 0

    while True:
        fund = FUNDS[cur_fund]
        next_div = None
        for d in fund["div"]:
            if d["basis"] >= entry_date:
                next_div = d
                break
        if next_div is None or next_div["exdiv"] > END_DATE:
            break

        div_usd = units*next_div["amount"]
        redirect_usd = div_usd*redirect_pct
        kept_usd = div_usd-redirect_usd
        total_cash_usd += kept_usd

        # 轉出申請日 = 除息日 + switch_delay_days；轉出/轉入NAV日 = 該日+settlement_days之後第一個可用交易日
        request_date = next_div["exdiv"] + timedelta(days=switch_delay_days)
        target_date = request_date + timedelta(days=settlement_days)
        idx_out, date_out, nav_out = nav_on_or_after(fund["nav"], target_date)
        if nav_out is None:
            total_cash_usd -= kept_usd  # undo: this dividend cycle never settles within data range
            break
        usd_value = units*nav_out

        if redirect_usd > 0:
            idx_t, date_t, nav_t = nav_on_or_after(TECH["nav"], target_date)
            if nav_t:
                tech_units += (redirect_usd*FX)/nav_t

        next_fund_code = ORDER[(ORDER.index(cur_fund)+1)%3]
        idx_in, date_in, nav_in = nav_on_or_after(FUNDS[next_fund_code]["nav"], target_date)
        if nav_in is None:
            total_cash_usd -= kept_usd
            break
        new_units = usd_value/nav_in

        # 檢查是否來不及：新基金的下一個基準日 是否早於 我們實際轉入完成日(date_in)
        nf = FUNDS[next_fund_code]
        for d2 in nf["div"]:
            if d2["basis"] >= entry_date:
                if d2["basis"] < date_in:
                    missed += 1
                break

        cur_fund = next_fund_code
        units = new_units
        entry_date = date_in
        cycles += 1

    idx_last, date_last, nav_last = nav_on_or_after(FUNDS[cur_fund]["nav"], END_DATE)
    if date_last is None:
        date_last, nav_last = FUNDS[cur_fund]["nav"][-1]
    final_principal_usd = units*nav_last

    idxt, datet, navt = nav_on_or_after(TECH["nav"], END_DATE)
    if datet is None:
        datet, navt = TECH["nav"][-1]
    final_tech_twd = tech_units*navt

    return {
        "cycles": cycles,
        "final_principal_twd": final_principal_usd*FX,
        "cash_twd": total_cash_usd*FX,
        "tech_twd": final_tech_twd,
        "total_twd": final_principal_usd*FX + final_tech_twd + total_cash_usd*FX,
        "invested_only_twd": final_principal_usd*FX + final_tech_twd,
        "missed": missed,
    }

print("="*100)
print("Q1: 轉換延遲天數敏感度分析 (除息日後第幾天才執行轉換)")
print("="*100)
for delay in [0,1,2,3,4,5,7,10,14]:
    r = simulate(switch_delay_days=delay, redirect_pct=0.0, settlement_days=0)
    print(f"延遲{delay:>2}天: 循環{r['cycles']:>2}次  本金期末市值=TWD{r['final_principal_twd']:>10,.0f}  配息現金=TWD{r['cash_twd']:>10,.0f}  總計=TWD{r['total_twd']:>10,.0f}  漏配息次數={r['missed']}")

print("\n"+"="*100)
print("Q2: 保單『贖回款項日數』對能否趕上下一檔配息的影響 (假設除息日當天送出申請,delay=0)")
print("="*100)
for settle in [0,1,2,3,4,5,6,7,8,9,10,12,15]:
    r = simulate(switch_delay_days=0, redirect_pct=0.0, settlement_days=settle)
    print(f"贖回款項日數={settle:>2}天: 循環{r['cycles']:>2}次  本金期末市值=TWD{r['final_principal_twd']:>10,.0f}  漏配息次數={r['missed']}")

print("\n"+"="*100)
print("Q3: 每筆配息轉出比例到安聯台灣科技 -> 需要多少%才能讓『本金+科技基金』不被侵蝕(>=100萬)")
print("="*100)
for pct in [0,10,20,30,40,50,60,70,80,90,100]:
    r = simulate(switch_delay_days=0, redirect_pct=pct/100, settlement_days=0)
    erosion = r['invested_only_twd']-PRINCIPAL_TWD
    print(f"轉出{pct:>3}%: 本金市值=TWD{r['final_principal_twd']:>9,.0f}  科技基金市值=TWD{r['tech_twd']:>9,.0f}  本金+科技={r['invested_only_twd']:>10,.0f}  留存現金=TWD{r['cash_twd']:>9,.0f}  vs原始100萬 {erosion:>+10,.0f}  總資產(含現金)={r['total_twd']:>10,.0f}")

# 精細搜尋臨界比例
print("\n精細搜尋臨界比例 (本金+科技基金 = 100萬 的轉出%):")
lo, hi = 0.0, 1.0
for _ in range(40):
    mid = (lo+hi)/2
    r = simulate(redirect_pct=mid)
    if r['invested_only_twd'] < PRINCIPAL_TWD:
        lo = mid
    else:
        hi = mid
print(f"臨界轉出比例 約 {hi*100:.2f}%  (此比例下 本金+科技基金 期末 = TWD {simulate(redirect_pct=hi)['invested_only_twd']:,.0f})")
