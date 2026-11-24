"""
Build excel/ops_cost_model.xlsx from the exported reporting files (run src/export_reporting.py first).

Sheets:
  Read me            what the model answers and how to use it
  Assumptions        every input in one place (blue = typed input, yellow = assumption to agree with ops)
  Fleet Economics    own van vs 3PL cost per trip, break-even, and a fleet-mix table per city
  Forecast           weekly completed tasks Jan-Jun, linear trend to September, riders and vans needed
  Pilot              Noida route restructuring: what-if before rollout vs measured result against Gurugram
  Data_*             values exported from PostgreSQL (do not edit)

All results are Excel formulas, so changing an assumption updates the model.

Usage:
    python src/build_cost_model.py
"""
import csv
from pathlib import Path

from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.formatting.rule import FormulaRule
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

ROOT = Path(__file__).resolve().parents[1]
REP = ROOT / "reporting"
OUT = ROOT / "excel" / "ops_cost_model.xlsx"

BLUE = Font(color="0000FF")
GREEN = Font(color="008000")
BOLD = Font(bold=True)
TITLE = Font(bold=True, size=14)
YELLOW = PatternFill("solid", fgColor="FFFF00")
HEAD = PatternFill("solid", fgColor="DDE2E8")
INR = '#,##0;(#,##0);"-"'
INR2 = '#,##0.00;(#,##0.00);"-"'
NUM2 = '0.00'
PCT = '0.0%;(0.0%);"-"'
CITIES = ["NOI", "GGN", "BLR"]
CITY_NAMES = {"NOI": "Noida", "GGN": "Gurugram", "BLR": "Bengaluru"}


def read(name):
    with open(REP / f"{name}.csv", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def head(ws, row, values, col=1):
    for i, v in enumerate(values):
        c = ws.cell(row=row, column=col + i, value=v)
        c.font = BOLD
        c.fill = HEAD
        c.alignment = Alignment(wrap_text=True, vertical="top")


def widths(ws, w):
    for i, x in enumerate(w, start=1):
        ws.column_dimensions[get_column_letter(i)].width = x


wb = Workbook()

# ------------------------------------------------------------------ data sheets (values)
fleet = {r["city_code"]: r for r in read("fleet_inputs")}
d = wb.active
d.title = "Data_Fleet"
cols = ["city_code", "own_vans", "tpl_vans", "own_trips_per_month", "tpl_trips_per_month", "km_per_trip",
        "own_trips_per_van_day", "days_observed"]
head(d, 1, cols)
for i, c in enumerate(CITIES, start=2):
    d.cell(row=i, column=1, value=c)
    for j, k in enumerate(cols[1:], start=2):
        d.cell(row=i, column=j, value=float(fleet[c][k]))
d.cell(row=6, column=1, value="Source: rpt.fleet_inputs (trip log, April to June 2025, after the diesel revision)")
widths(d, [12, 10, 10, 20, 20, 12, 20, 14])

weekly = read("weekly_volume")
weeks = sorted({r["week_start"] for r in weekly})
dw = wb.create_sheet("Data_Weekly")
head(dw, 1, ["week_no", "week_start"] + [f"{c}_tasks" for c in CITIES] + [f"{c}_trips" for c in CITIES]
         + [f"{c}_trip_hours" for c in CITIES])
idx = {(r["week_start"], r["city_code"]): r for r in weekly}
for i, w in enumerate(weeks, start=1):
    dw.cell(row=i + 1, column=1, value=i)
    dw.cell(row=i + 1, column=2, value=w)
    for j, c in enumerate(CITIES):
        dw.cell(row=i + 1, column=3 + j, value=int(idx[(w, c)]["completed_tasks"]))
        dw.cell(row=i + 1, column=6 + j, value=int(idx[(w, c)]["trips"]))
        dw.cell(row=i + 1, column=9 + j, value=float(idx[(w, c)]["avg_trip_hours"]))
N = len(weeks)
dw.cell(row=N + 3, column=1, value="Source: rpt.weekly_volume (full weeks, Monday start, 6 Jan to 29 Jun 2025)")
widths(dw, [9, 12] + [12] * 9)

pilot = {(r["month"], r["city_code"]): r for r in read("pilot_inputs")}
months = sorted({m for m, _ in pilot})
dp = wb.create_sheet("Data_Pilot")
head(dp, 1, ["month", "NOI_tasks", "NOI_km_loaded", "GGN_tasks", "GGN_km_loaded"])
for i, m in enumerate(months, start=2):
    dp.cell(row=i, column=1, value=m)
    dp.cell(row=i, column=2, value=int(pilot[(m, "NOI")]["tasks"]))
    dp.cell(row=i, column=3, value=float(pilot[(m, "NOI")]["km_loaded"]))
    dp.cell(row=i, column=4, value=int(pilot[(m, "GGN")]["tasks"]))
    dp.cell(row=i, column=5, value=float(pilot[(m, "GGN")]["km_loaded"]))
dp.cell(row=9, column=1, value="Source: rpt.pilot_inputs (trip log). Pilot: Noida routes restructured from 1 June 2025.")
widths(dp, [10, 12, 15, 12, 15])

# ------------------------------------------------------------------ assumptions
a = wb.create_sheet("Assumptions", 0)
a["A1"] = "Assumptions"
a["A1"].font = TITLE
a["A2"] = "Blue = typed input. Yellow = operating assumption to agree with operations before using the result."
head(a, 4, ["Input", "Value", "Unit", "Source / note"])
inputs = [
    # key, label, value, unit, note, yellow
    ("diesel", "Diesel price (from April 2025)", 101, "INR per litre", "ref.fuel_rates, revised in April 2025", False),
    ("litres_km", "Own van fuel use", 0.11, "litres per km", "ref.cost_parameters", False),
    ("van_fixed", "Own van lease and maintenance", 18000, "INR per van per month", "ref.cost_parameters", False),
    ("driver", "Own van driver", 20000, "INR per van per month", "Assumption: a 3PL van comes with its driver; an own van needs one", True),
    ("tpl_trip", "3PL rate per trip", 450, "INR per trip", "ref.rate_cards, V01 contract", False),
    ("tpl_km", "3PL rate per km", 14, "INR per km", "ref.rate_cards, V01 contract", False),
    ("days_month", "Operating days per month", 30, "days", "The operation runs every day", False),
    ("max_trips_van", "Maximum trips per own van per day", 4, "trips", "Assumption: about 2.8 hours per trip in a 12-hour day", True),
    ("rider_hours", "Rider on-duty hours per day", 8.5, "hours", "Own riders 9 h, contract riders 8 h", False),
    ("idle_allow", "Rider idle allowance", 0.15, "share of on-duty hours", "Assumption: loading, breaks, waiting for slots", True),
    ("pilot_target", "Planned reduction in km per task (what-if before rollout)", 0.10, "share", "Assumption: route-planning estimate before the pilot", True),
]
NAMES = {}
for i, (key, label, val, unit, note, yellow) in enumerate(inputs, start=5):
    a.cell(row=i, column=1, value=label)
    c = a.cell(row=i, column=2, value=val)
    c.font = BLUE
    if yellow:
        c.fill = YELLOW
    c.number_format = PCT if unit.startswith("share") else ('#,##0' if isinstance(val, int) else '#,##0.00')
    a.cell(row=i, column=3, value=unit)
    a.cell(row=i, column=4, value=note)
    NAMES[key] = f"Assumptions!$B${i}"
widths(a, [52, 12, 24, 70])

# ------------------------------------------------------------------ fleet economics
f = wb.create_sheet("Fleet Economics", 1)
f["A1"] = "Own van vs 3PL: cost per trip, break-even and fleet mix (April to June 2025 volumes)"
f["A1"].font = TITLE
f["A2"] = ("Both options carry a Kestrel rider for the deliveries, so rider cost is the same and left out. "
           "Own van = lease + maintenance + driver + fuel. 3PL = per trip + per km.")
head(f, 3, ["Measure"] + [CITY_NAMES[c] for c in CITIES])
rows = [
    ("Km per trip", lambda c, r: f"=Data_Fleet!F{r}", NUM2),
    ("Own vans today", lambda c, r: f"=Data_Fleet!B{r}", "0"),
    ("Own van trips per month", lambda c, r: f"=Data_Fleet!D{r}", "#,##0"),
    ("3PL trips per month", lambda c, r: f"=Data_Fleet!E{r}", "#,##0"),
    ("Trips per own van per month", lambda c, r: f"={c}6/{c}5", "#,##0.0"),
    ("Own van fuel cost per trip (INR)", lambda c, r: f"={c}4*{NAMES['litres_km']}*{NAMES['diesel']}", INR2),
    ("Own van fixed cost per month (INR)", lambda c, r: f"={NAMES['van_fixed']}+{NAMES['driver']}", INR),
    ("Own van fixed cost per trip (INR)", lambda c, r: f"={c}10/{c}8", INR2),
    ("Own van cost per trip (INR)", lambda c, r: f"={c}9+{c}11", INR2),
    ("3PL cost per trip (INR)", lambda c, r: f"={NAMES['tpl_trip']}+{NAMES['tpl_km']}*{c}4", INR2),
    ("Saving per trip on an own van (INR)", lambda c, r: f"={c}13-{c}12", INR2),
    ("Break-even trips per own van per month", lambda c, r: f"={c}10/({c}13-{c}9)", "#,##0.0"),
    ("Own van capacity per month (trips)", lambda c, r: f"={NAMES['max_trips_van']}*{NAMES['days_month']}", "#,##0"),
    ("Verdict at today's use", lambda c, r: f'=IF({c}8>{c}15,"Own van cheaper","3PL cheaper")', None),
]
for i, (label, fn, fmt) in enumerate(rows, start=4):
    f.cell(row=i, column=1, value=label)
    for j, city in enumerate(CITIES):
        col = get_column_letter(2 + j)
        c = f.cell(row=i, column=2 + j, value=fn(col, 2 + j))
        if fmt:
            c.number_format = fmt
        if fn(col, 2 + j).startswith("=Data_"):
            c.font = GREEN
# Fleet-mix table: total monthly van cost for 0..10 own vans, rest of the trips on the 3PL
f["A20"] = "Fleet mix: total monthly van cost (INR) by number of own vans; trips the own vans cannot carry go to the 3PL"
f["A20"].font = BOLD
head(f, 21, ["Own vans"] + [CITY_NAMES[c] for c in CITIES])
for k in range(0, 11):
    r = 22 + k
    f.cell(row=r, column=1, value=k)
    for j in range(3):
        col = get_column_letter(2 + j)
        total = f"({col}$6+{col}$7)"
        own_trips = f"MIN({total},$A{r}*{col}$16)"
        f.cell(row=r, column=2 + j,
               value=f"=$A{r}*{col}$10+{own_trips}*{col}$9+({total}-{own_trips})*{col}$13").number_format = INR
f["A34"] = "Cheapest number of own vans"
f["A35"] = "Monthly cost at that number (INR)"
f["A36"] = "Monthly cost today (INR)"
f["A37"] = "Monthly saving vs today (INR)"
for j in range(3):
    col = get_column_letter(2 + j)
    f[f"{col}34"] = f"=INDEX($A$22:$A$32,MATCH(MIN({col}22:{col}32),{col}22:{col}32,0))"
    f[f"{col}35"] = f"=MIN({col}22:{col}32)"
    f[f"{col}35"].number_format = INR
    f[f"{col}36"] = f"={col}5*{col}10+{col}6*{col}9+{col}7*{col}13"
    f[f"{col}36"].number_format = INR
    f[f"{col}37"] = f"={col}36-{col}35"
    f[f"{col}37"].number_format = INR
    f.conditional_formatting.add(f"{col}22:{col}32", FormulaRule(formula=[f"{col}22=MIN({col}$22:{col}$32)"],
                                                                 fill=PatternFill("solid", fgColor="C6EFCE")))
f["A39"] = ("Read with care: the cheapest mix carries every trip on own vans at today's average volume. "
            "Peaks (weekends are about 25% busier) need spare capacity, which the 3PL gives without a fixed cost.")
widths(f, [48, 16, 16, 16])

# ------------------------------------------------------------------ forecast and capacity
fc = wb.create_sheet("Forecast", 2)
fc["A1"] = "Weekly completed tasks: actuals to June, linear trend to September, and the capacity it needs"
fc["A1"].font = TITLE
head(fc, 3, ["Week", "Week start", "Type"] + [CITY_NAMES[c] for c in CITIES])
for i in range(1, N + 14):
    r = 3 + i
    fc.cell(row=r, column=1, value=i)
    if i <= N:
        fc.cell(row=r, column=2, value=f"=Data_Weekly!B{i + 1}").font = GREEN
        fc.cell(row=r, column=3, value="Actual")
        for j in range(3):
            fc.cell(row=r, column=4 + j, value=f"=Data_Weekly!{get_column_letter(3 + j)}{i + 1}").font = GREEN
    else:
        fc.cell(row=r, column=2, value=f'=TEXT(DATEVALUE(B{r - 1})+7,"yyyy-mm-dd")')
        fc.cell(row=r, column=3, value="Forecast")
        for j in range(3):
            dcol = get_column_letter(3 + j)
            fc.cell(row=r, column=4 + j,
                    value=f"=ROUND(FORECAST($A{r},Data_Weekly!${dcol}$2:${dcol}${N + 1},Data_Weekly!$A$2:$A${N + 1}),0)")
    for j in range(3):
        fc.cell(row=r, column=4 + j).number_format = "#,##0"
last = 3 + N + 13
fc.cell(row=3 + N + 1, column=8, value="Trend: Excel FORECAST (least-squares line through the 25 weekly actuals)")

cap = last + 3
fc.cell(row=cap - 1, column=1, value="Capacity for the busiest forecast week (July to September)").font = BOLD
head(fc, cap, ["Measure", "", ""] + [CITY_NAMES[c] for c in CITIES])
cap_rows = [
    ("Busiest forecast week: completed tasks", lambda col, dcol: f"=MAX({col}{4 + N}:{col}{last})", "#,##0"),
    ("Tasks per day", lambda col, dcol: f"={col}{cap + 1}/7", "#,##0.0"),
    ("Completed tasks per trip (Apr-Jun actual)",
     lambda col, dcol: f"=SUM(Data_Weekly!{dcol}$15:{dcol}${N + 1})/SUM(Data_Weekly!{chr(ord(dcol) + 3)}$15:{chr(ord(dcol) + 3)}${N + 1})", NUM2),
    ("Trips per day", lambda col, dcol: f"={col}{cap + 2}/{col}{cap + 3}", "#,##0.0"),
    ("Average trip hours (Apr-Jun actual)",
     lambda col, dcol: f"=AVERAGE(Data_Weekly!{chr(ord(dcol) + 6)}$15:{chr(ord(dcol) + 6)}${N + 1})", NUM2),
    ("Riders needed", lambda col, dcol: f"=ROUNDUP({col}{cap + 4}*{col}{cap + 5}/({NAMES['rider_hours']}*(1-{NAMES['idle_allow']})),0)", "0"),
    ("Riders today (Jun)", lambda col, dcol: {"D": "=6", "E": "=6", "F": "=7"}[col], "0"),
    ("Vans needed (own + 3PL)", lambda col, dcol: f"=ROUNDUP({col}{cap + 4}/{NAMES['max_trips_van']},0)", "0"),
    ("Vans today (own + 3PL)", lambda col, dcol: f"=Data_Fleet!B{CITIES.index({'D': 'NOI', 'E': 'GGN', 'F': 'BLR'}[col]) + 2}+Data_Fleet!C{CITIES.index({'D': 'NOI', 'E': 'GGN', 'F': 'BLR'}[col]) + 2}", "0"),
    ("Riders to add", lambda col, dcol: f"=MAX(0,{col}{cap + 6}-{col}{cap + 7})", "0"),
    ("Vans to add", lambda col, dcol: f"=MAX(0,{col}{cap + 8}-{col}{cap + 9})", "0"),
]
for i, (label, fn, fmt) in enumerate(cap_rows, start=1):
    fc.cell(row=cap + i, column=1, value=label)
    for j in range(3):
        col = get_column_letter(4 + j)
        dcol = get_column_letter(3 + j)
        c = fc.cell(row=cap + i, column=4 + j, value=fn(col, dcol))
        c.number_format = fmt
        if label.startswith("Riders today"):
            c.font = BLUE
            c.comment = Comment("Riders active in June 2025 (ref.riders).", "model")
fc.cell(row=cap + 13, column=1,
        value="Riders needed = trips per day x trip hours / (on-duty hours x (1 - idle allowance)). Week 14 onwards = April to June.")
widths(fc, [44, 12, 10, 14, 14, 14, 4, 60])

# ------------------------------------------------------------------ pilot
p = wb.create_sheet("Pilot", 3)
p["A1"] = "Noida route restructuring: what-if before rollout, then the measured result against Gurugram"
p["A1"].font = TITLE
head(p, 3, ["Measure", "Noida (pilot)", "Gurugram (control)"])
pr = [
    ("Km per task, January to May (before)", "=SUM(Data_Pilot!C2:C6)/SUM(Data_Pilot!B2:B6)", "=SUM(Data_Pilot!E2:E6)/SUM(Data_Pilot!D2:D6)", '0.000'),
    ("Km per task, June (after)", "=Data_Pilot!C7/Data_Pilot!B7", "=Data_Pilot!E7/Data_Pilot!D7", '0.000'),
    ("Change in km per task", "=B5-B4", "=C5-C4", '0.000;-0.000'),
    ("Change in %", "=B6/B4", "=C6/C4", PCT),
]
for i, (label, x, y, fmt) in enumerate(pr, start=4):
    p.cell(row=i, column=1, value=label)
    p.cell(row=i, column=2, value=x).number_format = fmt
    p.cell(row=i, column=3, value=y).number_format = fmt
p["A9"] = "Measured effect"
p["A9"].font = BOLD
meas = [
    ("Pilot effect on km per task (Noida change minus Gurugram change)", "=B6-C6", '0.000;-0.000'),
    ("Pilot effect in %", "=B10/B4", PCT),
    ("Noida tasks in June", "=Data_Pilot!B7", "#,##0"),
    ("Km saved in June", "=-B10*B12", "#,##0"),
    ("Blended cost per km in Noida (INR)",
     f"=(Data_Fleet!D2*{NAMES['litres_km']}*{NAMES['diesel']}*Data_Fleet!F2+Data_Fleet!E2*{NAMES['tpl_km']}*Data_Fleet!F2)/((Data_Fleet!D2+Data_Fleet!E2)*Data_Fleet!F2)", INR2),
    ("Saving in June (INR)", "=B13*B14", INR),
    ("Saving per year at June volume (INR)", "=B15*12", INR),
]
for i, (label, x, fmt) in enumerate(meas, start=10):
    p.cell(row=i, column=1, value=label)
    p.cell(row=i, column=2, value=x).number_format = fmt
p["A18"] = "What-if before rollout"
p["A18"].font = BOLD
wi = [
    ("Planned reduction in km per task", f"={NAMES['pilot_target']}", PCT),
    ("Expected monthly tasks (May actual)", "=Data_Pilot!B6", "#,##0"),
    ("Expected km saved per month", "=B4*B19*B20", "#,##0"),
    ("Expected saving per month (INR)", "=B21*B14", INR),
    ("Measured saving vs expected", "=B15/B22", PCT),
]
for i, (label, x, fmt) in enumerate(wi, start=19):
    p.cell(row=i, column=1, value=label)
    p.cell(row=i, column=2, value=x).number_format = fmt
p["A25"] = ("Why a control city: Noida's km per task could fall for reasons unrelated to the pilot (season, mix). "
            "Subtracting Gurugram's change over the same months removes what both cities shared.")
p["A26"] = "Only km saved is counted. Loaded km only; the effect on empty return km is not claimed."
widths(p, [62, 16, 18])

# ------------------------------------------------------------------ read me
rm = wb.create_sheet("Read me", 0)
rm["A1"] = "Kestrel Rentals (fictional): last-mile cost model, synthetic data, January to June 2025"
rm["A1"].font = TITLE
notes = [
    "Questions this workbook answers:",
    "1. Fleet Economics: is an own van or a 3PL van cheaper per trip in each city, at what use does an own van break even, and what fleet mix is cheapest?",
    "2. Forecast: how many tasks to expect each week from July to September, and how many riders and vans the busiest week needs.",
    "3. Pilot: what the Noida route restructuring was expected to save, and what it saved when measured against Gurugram.",
    "",
    "How to use it: change the blue cells on the Assumptions sheet; every result recalculates.",
    "Yellow cells are operating assumptions (driver cost, maximum trips per van, idle allowance, planned pilot reduction) to agree with operations.",
    "Data_ sheets hold values exported from PostgreSQL by src/export_reporting.py. Rebuild with: python src/build_cost_model.py",
    "Colours: blue = typed input, black = formula, green = link to a Data_ sheet.",
]
for i, t in enumerate(notes, start=3):
    rm.cell(row=i, column=1, value=t)
widths(rm, [150])

OUT.parent.mkdir(exist_ok=True)
wb.save(OUT)
print(f"Saved {OUT.relative_to(ROOT)}")
