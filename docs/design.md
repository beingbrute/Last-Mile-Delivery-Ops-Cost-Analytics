# Design: Last-Mile Delivery Operations & Cost Analytics

> **All data in this project is synthetic.** Kestrel Rentals, its cities, riders, vehicles, vendors and amounts are invented to demonstrate the analysis. Vendor names are fictional. Currency: INR.

---

## 1. The business scenario

**Kestrel Rentals** (fictional) rents furniture and home appliances on monthly subscription. Every rental starts with a **delivery** and ends with a **pickup**, both done by the company's last-mile operation:

```
Customer order or return request
        ↓
Warehouse: pick, pack, dispatch (WH-NCR for Noida and Gurugram, WH-BLR for Bengaluru)
        ↓
Trip: own van or 3PL van, a rider and a helper, several tasks per trip
        ↓
Task outcome: delivered / picked up, failed (customer unavailable, address issue), or cancelled
        ↓
Costs: own fleet (fuel, maintenance), 3PL fleet (vendor invoice), rider and warehouse manpower, packaging
```

The ops strategy analyst's job: report how the operation performs and what it costs, explain deviations, find where money is leaking, and support network and vendor decisions.

**Period:** January to June 2025 (6 months). **Cities:** Noida, Gurugram, Bengaluru.

---

## 2. Data

| Dataset | Grain | Key fields |
|---|---|---|
| `cities`, `warehouses` | One row each | City, warehouse served, shift capacity |
| `riders` | One per rider | City, employment type (own / contract), hourly cost |
| `vehicles` | One per vehicle | City, owner (own / 3PL vendor), fuel type, capacity |
| `orders` | One per customer order or return | Order type (delivery / pickup), city, items, created time, promised slot |
| `tasks` | One per delivery or pickup attempt | Order, trip, status (completed / failed / cancelled), reason code, dispatch time, completed time |
| `trips` | One per vehicle trip | Vehicle, rider, warehouse, start / end time, km loaded, km empty, idle minutes, tasks |
| `shifts` | One per rider per day | Rider, hours on duty, hours on task |
| `warehouse_shifts` | One per warehouse per shift | Items picked, items dispatched, stock-out events |
| `fuel_rates` | One per month | Diesel / electricity rate (revised in April) |
| `vendors`, `rate_cards` | Vendor and contracted rates, effective-dated | Per trip, per km, per man-day, per unit |
| `purchase_orders`, `grns`, `invoices` | One per document line | Vendor, item, quantity, rate, amount, dates |
| `cost_ledger` | One per cost entry | Month, city, cost head, vendor, amount |

**Volume:** 51,898 orders, 53,957 task attempts, 10,294 trips, 22 riders (19 for the whole period plus 3 extra contract riders in Gurugram in April and May), 19 vans (13 own, 6 from the 3PL), 3 vendors, and 6 months of POs, GRNs and invoices. A trip serves one 2-hour slot in one zone, so riders and vans make several trips a day.

---

## 3. Metric definitions

| Metric | Definition |
|---|---|
| **On-time %** | Completed tasks finished within the promised slot ÷ completed tasks |
| **TAT (hours)** | Order created → task completed |
| **SLA breach** | Task completed after the end of the slot promised to the customer (late on the day, or done on a later attempt) |
| **First-attempt success %** | Orders completed on the first attempt ÷ orders attempted |
| **Failure rate** | Failed attempts ÷ attempts, by reason code |
| **Cancellation rate** | Cancelled orders ÷ orders, by reason code |
| **Warehouse throughput** | Items dispatched per warehouse shift |
| **Rider productivity** | Completed tasks per rider on-duty hour |
| **Rider idle %** | (On-duty hours − hours on task) ÷ on-duty hours |
| **Vehicle utilisation** | Loaded km ÷ total km; tasks per trip |
| **Cost per completed task** | Total last-mile cost ÷ completed tasks |
| **Cost per trip / per item handled** | Fleet cost ÷ trips; warehouse + packaging cost ÷ items dispatched |
| **City cost-to-serve** | All last-mile and warehouse cost allocated to a city ÷ its completed tasks |

Every metric is defined once, in SQL views, and reused by Excel, Google Sheets and Power BI.

---

## 4. Vendor controls

| Vendor (fictional) | Service | Billing basis |
|---|---|---|
| V01 SwiftHaul Logistics | 3PL vans with driver | Per trip + per km, per the rate card |
| V02 BoxWorks Packaging | Cartons, bubble wrap, straps | Per unit, per PO |
| V03 StaffLine Services | Warehouse loaders | Per man-day |

**Checks**

| Code | Check |
|---|---|
| A01 | **Three-way match:** invoice quantity and rate vs PO vs GRN (goods received) |
| A02 | **Rate card:** billed rate vs the contracted rate in force on the service date |
| A03 | **Trip log:** 3PL km and trips billed vs km and trips in the trip log |
| A04 | **Duplicate invoice:** same vendor, number or same amount and period |
| A05 | **Price above PO** |

Each failed check goes to an **escalation log** with the amount at stake, owner (procurement / finance) and status.

---

## 5. Planted problems (answer key kept separately)

| Month | Planted situation | Expected finding |
|---|---|---|
| Feb | WH-NCR stock-outs on two fast-moving items | Late dispatches and out-of-stock cancellations rise in Noida and Gurugram |
| Feb | Packaging PO for 10,000 units, 8,500 received, 10,000 invoiced | A01 GRN short: 1,500 units overbilled |
| Mar | 3PL invoice km about 9% above the trip log | A03 km overbilling |
| Mar | Empty return legs double on one Noida route | Vehicle utilisation drops; empty-km leakage sized |
| Apr | Diesel rate revised upward | Own-fleet fuel cost per km up about 10%; because fuel is a small share of cost-to-serve, cost per task barely moves |
| Apr | 3PL bills ₹2 per km above the contracted rate | A02 rate-card breach |
| Apr–May | Too many contract riders deployed in Gurugram | Rider idle % high; excess deployment sized |
| May | Warehouse manpower invoice submitted twice | A04 duplicate |
| May | Bengaluru delivery slots moved earlier | First-attempt success falls; "customer unavailable" failures rise |
| Jun | Packaging billed above PO price | A05 price above PO |
| Jun | Route restructuring piloted in Noida (Gurugram as control) | Km per task falls in Noida, not in Gurugram; savings measured |

Everything else is normal operating variation (weekday/weekend volume, seasonality, random failures).

---

## 6. Analysis and decisions

1. **Performance:** daily and weekly on-time %, TAT, SLA breaches, failures, cancellations and throughput by city and warehouse, with each deviation traced to its root cause.
2. **Productivity:** rider tasks per hour and idle %, vehicle utilisation, warehouse throughput.
3. **Unit economics:** cost per task, per trip and per item; city cost-to-serve; month-on-month cost by city, cost head and vendor with variance commentary (volume, rate and mix effects).
4. **Vendor audit:** checks A01–A05 and the escalation log.
5. **Leakage:** idle capacity, empty return km, excess rider deployment, overbilling, each sized in ₹ per month with a recommended fix.
6. **Business case (Excel):** in-house fleet vs 3PL by city, break-even volume, fleet mix.
7. **Forecast and capacity:** weekly volume forecast for July–September and the riders and vans it needs.
8. **What-if and pilot:** expected savings of the Noida route restructuring before rollout, then measured against Gurugram as a control after.

---

## 7. Deliverables

| Output | Tool |
|---|---|
| Schema, metric views, vendor checks | PostgreSQL |
| Data generator, loader, tests | Python (pandas, pytest) |
| Cost model, business case, forecast | Excel |
| Weekly ops MIS, refreshed automatically | Google Sheets + Apps Script (time trigger) |
| Ops and cost dashboards | Power BI |
| One-page leadership review | Markdown / PDF |

## 8. Build sessions

| Session | Output |
|---|---|
| 1 | This design, data generator and answer key, schema and load |
| 2 | Metric views, root causes, productivity, unit costs, vendor checks, leakage |
| 3 | Excel cost model and business case, forecast and capacity plan, what-if and pilot measurement |
| 4 | Power BI dashboards, Google Sheets MIS with Apps Script, leadership review, tests, README |

## 9. Out of scope

A real TMS, WMS or ERP, live GPS data, real vendor contracts, and actual procurement approvals. The project shows the analysis and the controls, not experience inside a real logistics company.
