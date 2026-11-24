# Leadership review: last-mile operations, January to June 2025

Kestrel Rentals (fictional company, synthetic data). Every figure comes from the SQL views in this repository and is cross-checked in Excel, Power BI and the weekly MIS.

## Summary

| | Jan–Jun 2025 |
|---|---|
| Tasks completed | 49,852 |
| On time | 91.5% |
| Failed attempts | 5.0% |
| Total last-mile cost | ₹1.83 crore |
| Cost per completed task | ₹367 |
| Vendor overbilling found | ₹5.98 lakh (8 findings, all open) |
| Total leakage sized | ₹7.56 lakh |

Three things need a decision: recover the vendor overbilling, change the fleet mix, and plan riders for July to September (section 4).

## 1. What went wrong, and why

| When | What we saw | Root cause | Impact | Action |
|---|---|---|---|---|
| Feb | On-time fell to 74.7% in Noida and 78.5% in Gurugram (normal: about 93%) | Stock-outs of two fast-moving items at WH-NCR: 201 trips left the warehouse after the slot had started, 130 orders were cancelled as out of stock | 786 late tasks; worst day 6 Feb, 25% on time | Safety stock for fast movers; daily stock-out alert to the dispatch lead |
| Mar | Empty return km on Noida zone Z2 rose to 33.2% | Return legs doubled on one route | ₹9,510 in March | Re-plan the Z2 return route |
| Apr–May | Gurugram ran 9 riders instead of 6; idle time 27–29% | Three extra contract riders deployed ahead of demand | ₹95,040 added in April; about ₹73,600 of idle capacity over the two months | Approve contract riders against the volume forecast |
| May | Bengaluru failed attempts rose to 10.7% (was about 4%) | Delivery slots moved to 8:00 and 9:00; those slots fail 16–17%, mostly "customer unavailable" | About 300 extra failed attempts a month, each needing a second trip | Restore later slots, or confirm availability the evening before |
| May | Cost per task in Noida and Gurugram reached ₹423 and ₹441 | StaffLine billed the same month's loader invoice twice | ₹4.65 lakh | Reject the duplicate; add a duplicate check before payment |
| Apr | Own-fleet fuel cost per km rose 9.8% (₹10.12 to ₹11.11) | Diesel price revision | Small effect on cost per task, because fuel is a small share of total cost | None needed; watch |

## 2. Vendor findings

| Check | Vendor | Finding | Amount at stake |
|---|---|---|---|
| A04 Duplicate invoice | StaffLine Services | May loader invoice submitted twice | ₹4,65,000 |
| A01 Three-way match | BoxWorks Packaging | 10,000 cartons invoiced, 8,500 received (Feb) | ₹57,000 |
| A02 Rate card | SwiftHaul Logistics | ₹16 per km billed against a contracted ₹14 (Apr, 3 invoices) | ₹39,565 |
| A05 Price above PO | BoxWorks Packaging | Cartons billed at ₹42 against a PO rate of ₹38 (Jun) | ₹20,000 |
| A03 Trip log | SwiftHaul Logistics | Km billed about 9% above the trip log (Mar, 2 invoices) | ₹16,783 |
| | | **Total** | **₹5,98,348** |

All 8 are in the escalation log with an owner (procurement or accounts payable) and a due date.

## 3. What worked: Noida route pilot

New routes were piloted in Noida in June, with Gurugram as the control city.

- Km per task fell 12.4% in Noida and 1.2% in Gurugram, so the pilot's own effect is **−11.2%** (0.64 km per task).
- That saved 1,786 km and **₹21,519 in June**, about **₹2.58 lakh a year** at June volume.
- The plan before rollout expected a 10% reduction (₹19,581 a month); the result was 110% of plan.
- Only one month of data, and only variable km cost is counted. Recommend running it for two more months before rolling it out to Gurugram and Bengaluru.

## 4. Decisions requested

**a. Recover ₹5.98 lakh from vendors** and add two controls before payment: a duplicate-invoice check, and matching every packaging invoice to the goods-received note.

**b. Fleet mix.** An own van costs less per trip than a 3PL van in all three cities (₹772–857 against ₹917–973, April–June).

| | Noida | Gurugram | Bengaluru |
|---|---|---|---|
| Own vans today | 4 | 4 | 5 |
| Cheapest mix | 5 own | 5 own | 5 own |
| Saving per month | ₹61,267 | ₹65,178 | ₹95,236 |

Noida and Gurugram would each add one own van. Bengaluru already has five: its saving comes from using them more (about 86 trips per van a month, against a capacity of 120) before booking the 3PL. Keep the 3PL contract for peak days; weekends run about 25% busier than the average this mix is sized on.

**c. Riders for July to September.** On the current trend the busiest week reaches 660 / 755 / 745 tasks in Noida / Gurugram / Bengaluru. That needs **2 / 3 / 2 more riders** and no more vans. Hire as volume arrives: Gurugram's nine riders in April were the right number for September, four months early.

## 5. Limits

- Synthetic data, built to test the analysis; it is not a real company's operation.
- Assumptions not in the data: an own van needs a driver (₹20,000 a month), at most 4 trips per van per day, 15% rider idle allowance, 22% empty-km threshold. They are marked in the Excel model and can be changed there.
- The forecast is a straight-line trend on 25 weeks; it does not include festival-season peaks.
