import csv, math, os
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))

rows = []
with open(f"{BASE}\\rotation_log.csv", encoding="utf-8-sig") as f:
    r = csv.DictReader(f)
    for row in r:
        rows.append(row)

# principal mark-to-market right after each conversion = units_held * nav_out... reconstruct via held units * convert NAV
# we stored 轉換日NAV and 持有單位數 (units before conversion, at the fund being exited)
start_date = datetime(2024,7,24).date()
points = []  # (days_since_start, usd_value)
principal_usd0 = 1_000_000/31.5

# value right after initial purchase
points.append((0, principal_usd0))

with open(f"{BASE}\\rotation_log.csv", encoding="utf-8-sig") as f:
    r = csv.DictReader(f)
    for row in r:
        exdiv = datetime.strptime(row["除息日"], "%Y-%m-%d").date()
        units_held = float(row["持有單位數"])
        nav_out = float(row["轉換日NAV"])
        usd_value = units_held * nav_out
        days = (exdiv - start_date).days
        points.append((days, usd_value))

print(f"資料點數: {len(points)}  (起始 + 每次轉換)")
print(f"首筆: day0 = {points[0][1]:.2f} USD")
print(f"末筆: day{points[-1][0]} = {points[-1][1]:.2f} USD")

# linear regression of ln(value) vs days
xs = [p[0] for p in points]
ys = [math.log(p[1]) for p in points]
n = len(xs)
mean_x = sum(xs)/n
mean_y = sum(ys)/n
cov = sum((x-mean_x)*(y-mean_y) for x,y in zip(xs,ys))
varx = sum((x-mean_x)**2 for x in xs)
slope = cov/varx   # ln(value) change per day
intercept = mean_y - slope*mean_x

daily_decay = math.exp(slope)
annual_decay = daily_decay**365
print(f"\n回歸結果：每日衰減係數 = {daily_decay:.6f}  =>  年化衰減率 = {(1-annual_decay)*100:.2f}% / 年")
print(f"等同於年化報酬率(只看本金，不含配息): {(annual_decay-1)*100:.2f}%")

# R^2
ss_tot = sum((y-mean_y)**2 for y in ys)
ss_res = sum((y - (intercept+slope*x))**2 for x,y in zip(xs,ys))
r2 = 1 - ss_res/ss_tot
print(f"回歸 R^2 = {r2:.4f} (數據點對這條趨勢線的貼合程度)")

# project forward: days to reach various thresholds of original principal
V0 = principal_usd0
print(f"\n若依此年化趨勢線性外推（注意：純數學外推，不是保證），本金降到以下水準所需時間：")
for pct in [50, 25, 10, 5, 1]:
    target = V0 * pct/100
    # ln(target) = intercept + slope*days  => days = (ln(target)-intercept)/slope
    days_needed = (math.log(target) - intercept)/slope
    years_needed = days_needed/365
    print(f"  剩 {pct:>3}%本金 (USD {target:>10,.0f} / TWD {target*31.5:>11,.0f}):  約 {years_needed:>5.1f} 年後 (距今約 {years_needed-2:.1f} 年後)")

# also naive endpoint-to-endpoint method for comparison
v_start = points[0][1]
v_end = points[-1][1]
days_total = points[-1][0]
naive_daily = (v_end/v_start)**(1/days_total)
naive_annual = naive_daily**365
print(f"\n(對照：單純頭尾相除法 年化衰減率 = {(1-naive_annual)*100:.2f}%/年，跟回歸法应該相近)")
