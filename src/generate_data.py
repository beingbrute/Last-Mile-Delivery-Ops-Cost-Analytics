"""
Synthetic operations data for Kestrel Rentals (fictional), January to June 2025.

Writes to data/raw/:
  reference/  cities, warehouses, riders, vehicles, vendors, rate_cards, fuel_rates
  ops/        orders, tasks, trips, rider_shifts, warehouse_shifts
  vendor/     purchase_orders, grns, invoices
and data/answer_key/expected_findings.csv (used only by the tests).

The planted problems are listed in docs/design.md (section 5). Everything else is normal variation.
Deterministic: the same seed gives the same files.
"""
import csv
import math
import random
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
KEY = ROOT / "data" / "answer_key" / "expected_findings.csv"
rng = random.Random(2025)

START, END = date(2025, 1, 1), date(2025, 6, 30)
CITIES = {   # code: name, warehouse, base orders a day, riders (own, contract), vehicles (own, 3PL)
    "NOI": ("Noida", "WH-NCR", 78, (4, 2), (4, 2)),
    "GGN": ("Gurugram", "WH-NCR", 86, (4, 2), (4, 2)),
    "BLR": ("Bengaluru", "WH-BLR", 92, (5, 2), (5, 2)),
}
WAREHOUSES = {"WH-NCR": ("NCR Warehouse, Noida", 10), "WH-BLR": ("Bengaluru Warehouse", 7)}  # loaders per shift
ZONES = ["Z1", "Z2", "Z3"]
SLOT_STARTS = [9, 11, 13, 15, 17, 19]
SLOT_STARTS_BLR_MAY = [8, 8, 9, 9, 11, 13, 15, 17]          # planted: Bengaluru slots moved earlier from May
OWN_SALARY_MONTH = 21000          # own rider, per month
CONTRACT_RIDER_HOUR = 135         # contract rider, per on-duty hour
OWN_VAN_FIXED_MONTH = 18000       # lease + maintenance per own van per month
DIESEL_L_PER_KM = 0.11
PACKAGING_UNITS_PER_ITEM = 1.2

# Vendor contract rates (effective-dated rate cards)
RATES = [
    ("V01", "TRIP", "Per trip", 450.0, "2025-01-01", "2025-12-31"),
    ("V01", "KM", "Per km", 14.0, "2025-01-01", "2025-12-31"),
    ("V02", "CARTON", "Packaging unit", 38.0, "2025-01-01", "2025-12-31"),
    ("V03", "MANDAY", "Loader man-day", 750.0, "2025-01-01", "2025-12-31"),
]
FUEL = [(m, 92.0 if m <= 3 else 101.0) for m in range(1, 7)]          # planted: diesel revised from April


def write(path, rows, cols):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)


def days():
    d = START
    while d <= END:
        yield d
        d += timedelta(days=1)


def ts(d, minutes):
    return datetime.combine(d, datetime.min.time()) + timedelta(minutes=round(minutes))


# ------------------------------------------------------------------ reference
cities = [{"city_code": c, "city_name": v[0], "warehouse_code": v[1]} for c, v in CITIES.items()]
warehouses = [{"warehouse_code": w, "warehouse_name": v[0], "loaders_per_shift": v[1]} for w, v in WAREHOUSES.items()]
riders, vehicles = [], []
for c, (_, _, _, (own, con), (own_v, tpl_v)) in CITIES.items():
    for i in range(own):
        riders.append({"rider_id": f"R-{c}-{len(riders) + 1:03d}", "city_code": c, "employment": "Own",
                       "active_from": "2025-01-01", "active_to": "2025-06-30"})
    for i in range(con):
        riders.append({"rider_id": f"R-{c}-{len(riders) + 1:03d}", "city_code": c, "employment": "Contract",
                       "active_from": "2025-01-01", "active_to": "2025-06-30"})
    for i in range(own_v):
        vehicles.append({"vehicle_id": f"V-{c}-{len(vehicles) + 1:03d}", "city_code": c, "owner": "Own",
                         "vendor_code": "", "fuel": "Diesel"})
    for i in range(tpl_v):
        vehicles.append({"vehicle_id": f"V-{c}-{len(vehicles) + 1:03d}", "city_code": c, "owner": "3PL",
                         "vendor_code": "V01", "fuel": "Diesel"})
# planted: 3 extra contract riders deployed in Gurugram for April and May without extra volume
for i in range(3):
    riders.append({"rider_id": f"R-GGN-{len(riders) + 1:03d}", "city_code": "GGN", "employment": "Contract",
                   "active_from": "2025-04-01", "active_to": "2025-05-31"})
vendors = [{"vendor_code": "V01", "vendor_name": "SwiftHaul Logistics", "service": "3PL vans with driver"},
           {"vendor_code": "V02", "vendor_name": "BoxWorks Packaging", "service": "Packaging"},
           {"vendor_code": "V03", "vendor_name": "StaffLine Services", "service": "Warehouse loaders"}]
rate_cards = [{"vendor_code": v, "rate_code": rc, "description": d, "rate": r, "valid_from": f, "valid_to": t}
              for v, rc, d, r, f, t in RATES]
fuel_rates = [{"month": f"2025-{m:02d}", "diesel_per_litre": r} for m, r in FUEL]
rate = {(v, rc): r for v, rc, _, r, _, _ in RATES}

# ------------------------------------------------------------------ orders, tasks, trips
orders, tasks, trips, shifts, wh_shifts = [], [], [], [], []
due = {c: {} for c in CITIES}            # city -> service date -> list of (order_id, attempt)
order_info = {}
n_order = n_task = n_trip = 0
stockout_days = {d for d in days() if d.month == 2 and d.day in range(3, 25) and rng.random() < 0.55}

for d in days():
    growth = 1 + 0.02 * (d.month - 1)
    weekend = 1.25 if d.weekday() >= 5 else 1.0
    for c, (name, wh, base, _, _) in CITIES.items():
        n = round(rng.gauss(base * growth * weekend, base * 0.08))
        for _ in range(max(n, 0)):
            n_order += 1
            oid = f"O{n_order:06d}"
            otype = "Delivery" if rng.random() < 0.56 else "Pickup"
            created = ts(d, rng.uniform(8 * 60, 22 * 60))
            serve = d + timedelta(days=1 if rng.random() < 0.7 else 2)
            starts = SLOT_STARTS_BLR_MAY if (c == "BLR" and serve.month >= 5) else SLOT_STARTS
            slot = rng.choice(starts)
            zone = rng.choice(ZONES)
            items = rng.choices([1, 2, 3, 4], [35, 35, 20, 10])[0]
            o = {"order_id": oid, "order_type": otype, "city_code": c, "zone": zone, "items": items,
                 "created_at": created, "promised_date": serve, "slot_start_hour": slot}
            orders.append({**o, "promised_date": serve.isoformat(), "created_at": created.isoformat(sep=" ")})
            order_info[oid] = o
            if serve <= END:
                due[c].setdefault(serve, []).append((oid, 1))

for d in days():
    for c, (name, wh, base, (own_r, con_r), (own_v, tpl_v)) in CITIES.items():
        jobs = due[c].get(d, [])
        if not jobs:
            continue
        live = []
        for oid, attempt in jobs:
            o = order_info[oid]
            n_task += 1
            t = {"task_id": f"T{n_task:06d}", "order_id": oid, "attempt": attempt, "service_date": d.isoformat(),
                 "trip_id": "", "status": "", "reason": "", "completed_at": ""}
            out_of_stock = (o["order_type"] == "Delivery" and wh == "WH-NCR" and d in stockout_days
                            and rng.random() < 0.10)
            if out_of_stock:
                t.update(status="Cancelled", reason="Out of stock")
            elif rng.random() < 0.025:
                t.update(status="Cancelled", reason="Customer cancelled")
            else:
                live.append(t)
            tasks.append(t)
        # build trips: one trip per slot and zone, at most 9 tasks
        groups = {}
        for t in live:
            o = order_info[t["order_id"]]
            groups.setdefault((o["slot_start_hour"], o["zone"]), []).append(t)
        chunks = []
        for key in sorted(groups):
            g = groups[key]
            n_chunks = math.ceil(len(g) / 9)
            size = math.ceil(len(g) / n_chunks)
            chunks += [g[i:i + size] for i in range(0, len(g), size)]
        city_riders = [r for r in riders if r["city_code"] == c
                       and r["active_from"] <= d.isoformat() <= r["active_to"]]
        own_vans = [v for v in vehicles if v["city_code"] == c and v["owner"] == "Own"]
        tpl_vans = [v for v in vehicles if v["city_code"] == c and v["owner"] == "3PL"]
        rider_hours = {r["rider_id"]: 0.0 for r in city_riders}
        for j, chunk in enumerate(chunks):
            n_trip += 1
            trip_id = f"TR{n_trip:06d}"
            van = tpl_vans[(j // 3) % len(tpl_vans)] if j % 3 == 2 else own_vans[j % len(own_vans)]
            rider = city_riders[j % len(city_riders)]
            zone = max(ZONES, key=lambda z: sum(order_info[t["order_id"]]["zone"] == z for t in chunk))
            first_slot = min(order_info[t["order_id"]]["slot_start_hour"] for t in chunk)
            start = first_slot * 60 - rng.uniform(40, 60)
            route_delay = rng.uniform(60, 120) if rng.random() < 0.10 else 0   # normal variation: traffic on the route
            late_dispatch = wh == "WH-NCR" and d in stockout_days and rng.random() < 0.45
            if late_dispatch:
                start += rng.uniform(90, 180)          # planted: waiting for stock at WH-NCR in February
            per_task_km = rng.uniform(3.5, 5.5)
            if c == "NOI" and d >= date(2025, 6, 1):
                per_task_km *= 0.86                     # planted: route restructuring pilot in Noida from June
            loaded_km = round(6 + len(chunk) * per_task_km, 1)
            empty_share = rng.uniform(0.18, 0.30)
            if c == "NOI" and zone == "Z2" and d.month == 3:
                empty_share *= 2.1                      # planted: empty return legs double on one Noida route in March
            empty_km = round(loaded_km * empty_share, 1)
            clock = start + rng.uniform(25, 40) + route_delay   # first drop
            done_ok = 0
            for t in chunk:
                o = order_info[t["order_id"]]
                slot_start = o["slot_start_hour"] * 60
                clock = max(clock + rng.uniform(10, 22), slot_start + rng.uniform(0, 15))
                p_unavail = 0.03
                if c == "BLR" and d.month >= 5 and o["slot_start_hour"] <= 9:
                    p_unavail = 0.16                    # planted: early slots in Bengaluru from May
                r = rng.random()
                if r < p_unavail:
                    t.update(status="Failed", reason="Customer unavailable")
                elif r < p_unavail + 0.012:
                    t.update(status="Failed", reason="Address issue")
                else:
                    t.update(status="Completed", completed_at=ts(d, clock).isoformat(sep=" "))
                    done_ok += 1
                t["trip_id"] = trip_id
                if t["status"] == "Failed":
                    nxt = d + timedelta(days=1)
                    if t["attempt"] == 1 and nxt <= END:
                        due[c].setdefault(nxt, []).append((t["order_id"], 2))
            end = clock + rng.uniform(25, 50)
            idle = round(rng.uniform(10, 40))
            trips.append({"trip_id": trip_id, "service_date": d.isoformat(), "city_code": c, "warehouse_code": wh,
                          "zone": zone, "vehicle_id": van["vehicle_id"], "rider_id": rider["rider_id"],
                          "start_at": ts(d, start).isoformat(sep=" "), "end_at": ts(d, end).isoformat(sep=" "),
                          "tasks": len(chunk), "km_loaded": loaded_km, "km_empty": empty_km, "idle_minutes": idle})
            rider_hours[rider["rider_id"]] += (end - start) / 60
        for r in city_riders:
            on_duty = 9.0 if r["employment"] == "Own" else 8.0
            shifts.append({"service_date": d.isoformat(), "rider_id": r["rider_id"], "city_code": c,
                           "on_duty_hours": on_duty, "task_hours": round(min(rider_hours[r["rider_id"]], on_duty), 2)})

# warehouse shifts: items dispatched (deliveries on completed or failed trips) and returned (pickups completed)
by_wh_day = {}
for t in tasks:
    o = order_info[t["order_id"]]
    wh = CITIES[o["city_code"]][1]
    key = (wh, t["service_date"])
    agg = by_wh_day.setdefault(key, {"dispatched": 0, "returned": 0})
    if t["trip_id"] and o["order_type"] == "Delivery":
        agg["dispatched"] += o["items"]
    if t["status"] == "Completed" and o["order_type"] == "Pickup":
        agg["returned"] += o["items"]
for (wh, sd), agg in sorted(by_wh_day.items()):
    d = date.fromisoformat(sd)
    for shift, share in (("Morning", 0.6), ("Evening", 0.4)):
        stockouts = rng.randint(3, 8) if (wh == "WH-NCR" and d in stockout_days) else (1 if rng.random() < 0.05 else 0)
        wh_shifts.append({"service_date": sd, "warehouse_code": wh, "shift": shift,
                          "items_dispatched": round(agg["dispatched"] * share),
                          "items_returned": round(agg["returned"] * share),
                          "stockout_events": stockouts, "loaders": WAREHOUSES[wh][1]})

# ------------------------------------------------------------------ vendor documents
pos, grns, invoices, findings = [], [], [], []
n_doc = 0


def doc(prefix):
    global n_doc
    n_doc += 1
    return f"{prefix}-{n_doc:05d}"


def month_end(m):
    return date(2025, m, 28 if m == 2 else 30 if m in (4, 6) else 31)


for m in range(1, 7):
    me = month_end(m)
    ym = f"2025-{m:02d}"
    # V01 3PL: invoice per city from the trip log
    for c in CITIES:
        ct = [t for t in trips if t["city_code"] == c and t["service_date"].startswith(ym)
              and next(v for v in vehicles if v["vehicle_id"] == t["vehicle_id"])["owner"] == "3PL"]
        n_trips = len(ct)
        km = round(sum(t["km_loaded"] + t["km_empty"] for t in ct), 1)
        billed_km, km_rate = km, rate[("V01", "KM")]
        if m == 3 and c in ("NOI", "GGN"):
            billed_km = round(km * 1.09, 1)              # planted: km overbilled in March (NCR)
            findings.append({"check_code": "A03", "month": ym, "vendor_code": "V01", "scope": c,
                             "expected": "km billed above trip log", "amount_inr": round((billed_km - km) * km_rate, 2)})
        if m == 4:
            km_rate = rate[("V01", "KM")] + 2            # planted: per-km rate above contract in April
            findings.append({"check_code": "A02", "month": ym, "vendor_code": "V01", "scope": c,
                             "expected": "per-km rate above rate card", "amount_inr": round(billed_km * 2, 2)})
        inv = doc("SH")
        invoices.append({"invoice_no": inv, "vendor_code": "V01", "invoice_date": me.isoformat(), "service_month": ym,
                         "scope": c, "po_no": "", "item": "TRIP", "quantity": n_trips, "rate": rate[("V01", "TRIP")],
                         "amount": round(n_trips * rate[("V01", "TRIP")], 2)})
        invoices.append({"invoice_no": inv, "vendor_code": "V01", "invoice_date": me.isoformat(), "service_month": ym,
                         "scope": c, "po_no": "", "item": "KM", "quantity": billed_km, "rate": km_rate,
                         "amount": round(billed_km * km_rate, 2)})
    # V02 packaging and V03 loaders: per warehouse, PO -> GRN -> invoice
    for wh in WAREHOUSES:
        items = sum(s["items_dispatched"] for s in wh_shifts if s["warehouse_code"] == wh and s["service_date"].startswith(ym))
        units = int(math.ceil(items * PACKAGING_UNITS_PER_ITEM / 500.0) * 500)
        if m == 2 and wh == "WH-NCR":
            units = 10000
        po = doc("PO")
        pos.append({"po_no": po, "vendor_code": "V02", "warehouse_code": wh, "po_date": date(2025, m, 1).isoformat(),
                    "item": "CARTON", "quantity": units, "rate": rate[("V02", "CARTON")],
                    "amount": round(units * rate[("V02", "CARTON")], 2)})
        received = units
        if m == 2 and wh == "WH-NCR":
            received = 8500                              # planted: 1,500 cartons short, invoiced in full
            findings.append({"check_code": "A01", "month": ym, "vendor_code": "V02", "scope": wh,
                             "expected": "invoiced quantity above GRN", "amount_inr": round(1500 * rate[("V02", "CARTON")], 2)})
        grns.append({"grn_no": doc("GRN"), "po_no": po, "vendor_code": "V02", "warehouse_code": wh,
                     "grn_date": date(2025, m, 5).isoformat(), "item": "CARTON", "quantity_received": received})
        inv_rate = rate[("V02", "CARTON")]
        if m == 6 and wh == "WH-BLR":
            inv_rate = 42.0                              # planted: billed above PO price in June
            findings.append({"check_code": "A05", "month": ym, "vendor_code": "V02", "scope": wh,
                             "expected": "invoice rate above PO rate", "amount_inr": round(units * 4.0, 2)})
        invoices.append({"invoice_no": doc("BW"), "vendor_code": "V02", "invoice_date": date(2025, m, 10).isoformat(),
                         "service_month": ym, "scope": wh, "po_no": po, "item": "CARTON", "quantity": units,
                         "rate": inv_rate, "amount": round(units * inv_rate, 2)})
        mandays = sum(s["loaders"] for s in wh_shifts if s["warehouse_code"] == wh and s["service_date"].startswith(ym))
        po3 = doc("PO")
        pos.append({"po_no": po3, "vendor_code": "V03", "warehouse_code": wh, "po_date": date(2025, m, 1).isoformat(),
                    "item": "MANDAY", "quantity": mandays, "rate": rate[("V03", "MANDAY")],
                    "amount": round(mandays * rate[("V03", "MANDAY")], 2)})
        grns.append({"grn_no": doc("GRN"), "po_no": po3, "vendor_code": "V03", "warehouse_code": wh,
                     "grn_date": me.isoformat(), "item": "MANDAY", "quantity_received": mandays})
        inv = {"invoice_no": doc("SL"), "vendor_code": "V03", "invoice_date": me.isoformat(), "service_month": ym,
               "scope": wh, "po_no": po3, "item": "MANDAY", "quantity": mandays, "rate": rate[("V03", "MANDAY")],
               "amount": round(mandays * rate[("V03", "MANDAY")], 2)}
        invoices.append(inv)
        if m == 5 and wh == "WH-NCR":
            dup = {**inv, "invoice_no": inv["invoice_no"] + "-R", "invoice_date": (me + timedelta(days=4)).isoformat()}
            invoices.append(dup)                         # planted: the same invoice resubmitted
            findings.append({"check_code": "A04", "month": ym, "vendor_code": "V03", "scope": wh,
                             "expected": "duplicate invoice", "amount_inr": inv["amount"]})

# operational findings for the answer key (values checked by the tests within a tolerance)
for code, month, scope, text in [
    ("OPS-STOCKOUT", "2025-02", "WH-NCR", "late dispatches and out-of-stock cancellations"),
    ("OPS-EMPTY-KM", "2025-03", "NOI/Z2", "empty km share about double the usual"),
    ("OPS-FUEL", "2025-04", "Own fleet", "diesel 92 -> 101 per litre: own-fleet fuel cost per km up about 10%, small effect on cost per task"),
    ("OPS-IDLE", "2025-04..2025-05", "GGN", "3 extra contract riders; rider idle % up"),
    ("OPS-SLOTS", "2025-05..2025-06", "BLR", "early slots; customer-unavailable failures up"),
    ("OPS-PILOT", "2025-06", "NOI vs GGN", "km per task down about 10% in Noida, not in Gurugram"),
]:
    findings.append({"check_code": code, "month": month, "vendor_code": "", "scope": scope, "expected": text,
                     "amount_inr": ""})

# ------------------------------------------------------------------ write
for o in orders:
    o.pop("created_at_dt", None)
write(RAW / "reference" / "cities.csv", cities, ["city_code", "city_name", "warehouse_code"])
write(RAW / "reference" / "warehouses.csv", warehouses, ["warehouse_code", "warehouse_name", "loaders_per_shift"])
write(RAW / "reference" / "riders.csv", riders, ["rider_id", "city_code", "employment", "active_from", "active_to"])
write(RAW / "reference" / "vehicles.csv", vehicles, ["vehicle_id", "city_code", "owner", "vendor_code", "fuel"])
write(RAW / "reference" / "vendors.csv", vendors, ["vendor_code", "vendor_name", "service"])
write(RAW / "reference" / "rate_cards.csv", rate_cards,
      ["vendor_code", "rate_code", "description", "rate", "valid_from", "valid_to"])
write(RAW / "reference" / "fuel_rates.csv", fuel_rates, ["month", "diesel_per_litre"])
write(RAW / "reference" / "cost_parameters.csv", [
    {"parameter": "own_rider_salary_month", "value": OWN_SALARY_MONTH},
    {"parameter": "contract_rider_per_hour", "value": CONTRACT_RIDER_HOUR},
    {"parameter": "own_van_fixed_month", "value": OWN_VAN_FIXED_MONTH},
    {"parameter": "diesel_litres_per_km", "value": DIESEL_L_PER_KM},
], ["parameter", "value"])
write(RAW / "ops" / "orders.csv", orders, ["order_id", "order_type", "city_code", "zone", "items", "created_at",
                                           "promised_date", "slot_start_hour"])
write(RAW / "ops" / "tasks.csv", tasks, ["task_id", "order_id", "attempt", "service_date", "trip_id", "status",
                                         "reason", "completed_at"])
write(RAW / "ops" / "trips.csv", trips, ["trip_id", "service_date", "city_code", "warehouse_code", "zone", "vehicle_id",
                                         "rider_id", "start_at", "end_at", "tasks", "km_loaded", "km_empty",
                                         "idle_minutes"])
write(RAW / "ops" / "rider_shifts.csv", shifts, ["service_date", "rider_id", "city_code", "on_duty_hours", "task_hours"])
write(RAW / "ops" / "warehouse_shifts.csv", wh_shifts, ["service_date", "warehouse_code", "shift", "items_dispatched",
                                                        "items_returned", "stockout_events", "loaders"])
write(RAW / "vendor" / "purchase_orders.csv", pos, ["po_no", "vendor_code", "warehouse_code", "po_date", "item",
                                                    "quantity", "rate", "amount"])
write(RAW / "vendor" / "grns.csv", grns, ["grn_no", "po_no", "vendor_code", "warehouse_code", "grn_date", "item",
                                          "quantity_received"])
write(RAW / "vendor" / "invoices.csv", invoices, ["invoice_no", "vendor_code", "invoice_date", "service_month", "scope",
                                                  "po_no", "item", "quantity", "rate", "amount"])
write(KEY, findings, ["check_code", "month", "vendor_code", "scope", "expected", "amount_inr"])

print(f"orders {len(orders)}, task attempts {len(tasks)}, trips {len(trips)}, riders {len(riders)}, "
      f"vehicles {len(vehicles)}, rider shifts {len(shifts)}, warehouse shifts {len(wh_shifts)}")
print(f"POs {len(pos)}, GRNs {len(grns)}, invoice lines {len(invoices)}, answer-key rows {len(findings)}")
