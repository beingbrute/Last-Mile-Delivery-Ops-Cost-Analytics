# Data dictionary

Database `lastmile` (PostgreSQL). All data is synthetic. Amounts in INR.

## Source tables

### ref: reference data

| Table | Grain | Columns |
|---|---|---|
| `ref.warehouses` | One per warehouse | `warehouse_code` (WH-NCR, WH-BLR), `warehouse_name`, `loaders_per_shift` |
| `ref.cities` | One per city | `city_code` (NOI, GGN, BLR), `city_name`, `warehouse_code` |
| `ref.vendors` | One per vendor | `vendor_code` (V01 SwiftHaul 3PL, V02 BoxWorks packaging, V03 StaffLine loaders), `vendor_name`, `service` |
| `ref.riders` | One per rider | `rider_id`, `city_code`, `employment` (Own / Contract), `active_from`, `active_to` |
| `ref.vehicles` | One per van | `vehicle_id`, `city_code`, `owner` (Own / 3PL), `vendor_code` (3PL only), `fuel` |
| `ref.rate_cards` | One per vendor rate and period | `vendor_code`, `rate_code` (TRIP, KM, CARTON, MANDAY), `description`, `rate`, `valid_from`, `valid_to` |
| `ref.fuel_rates` | One per month | `month`, `diesel_per_litre` (92 to March, 101 from April) |
| `ref.cost_parameters` | One per parameter | `parameter`, `value`: own rider salary ₹21,000/month, contract rider ₹135/hour, own van lease and maintenance ₹18,000/month, diesel 0.11 litres/km |

### ops: operations

| Table | Grain | Columns |
|---|---|---|
| `ops.orders` | One per customer delivery or return pickup | `order_id`, `order_type` (Delivery / Pickup), `city_code`, `zone`, `items`, `created_at`, `promised_date`, `slot_start_hour` (start of a 2-hour slot) |
| `ops.tasks` | One per attempt at an order | `task_id`, `order_id`, `attempt`, `service_date`, `trip_id` (empty if cancelled before dispatch), `status` (Completed / Failed / Cancelled), `reason`, `completed_at` |
| `ops.trips` | One per van trip (one slot, one zone) | `trip_id`, `service_date`, `city_code`, `warehouse_code`, `zone`, `vehicle_id`, `rider_id`, `start_at`, `end_at`, `tasks`, `km_loaded`, `km_empty`, `idle_minutes` |
| `ops.rider_shifts` | One per rider per day | `service_date`, `rider_id`, `city_code`, `on_duty_hours`, `task_hours` |
| `ops.warehouse_shifts` | One per warehouse per shift | `service_date`, `warehouse_code`, `shift`, `items_dispatched`, `items_returned`, `stockout_events`, `loaders` |

### vnd: vendor documents

| Table | Grain | Columns |
|---|---|---|
| `vnd.purchase_orders` | One per PO | `po_no`, `vendor_code`, `warehouse_code`, `po_date`, `item`, `quantity`, `rate`, `amount` |
| `vnd.grns` | One per goods received note | `grn_no`, `po_no`, `vendor_code`, `warehouse_code`, `grn_date`, `item`, `quantity_received` |
| `vnd.invoices` | One per invoice line | `line_id`, `invoice_no`, `vendor_code`, `invoice_date`, `service_month`, `scope` (city for the 3PL, warehouse for packaging and loaders), `po_no` (empty for rate-card services), `item`, `quantity`, `rate`, `amount` |

## Reporting views (rpt)

Metric definitions are in `docs/design.md`, section 3. Rates are ratios of totals, not averages of daily rates.

| View | Grain | Main columns |
|---|---|---|
| `rpt.task_facts` (stored) | One per attempt | Order and slot fields, `slot_end`, `promised_slot_end`, `on_time`, `tat_hours` |
| `rpt.trip_facts` (stored) | One per trip | `owner`, `km_total`, `empty_share`, `trip_hours`, `first_slot_start`, `late_dispatch` (left after its first slot started), `completed` |
| `rpt.daily_ops` | Day × city | `attempts`, `first_attempts`, `completed`, `failed`, `cancelled`, `on_time`, `sla_breaches`, `avg_tat_hours` |
| `rpt.monthly_ops` | Month × city | Counts plus `on_time_pct`, `failure_pct`, `cancellation_pct`, `first_attempt_success_pct`, `avg_tat_hours` |
| `rpt.task_root_causes` | One per task late, failed or cancelled | `root_cause`: Cancelled / Failed with reason, Late: left the warehouse after the slot started, Late: delay on the route |
| `rpt.root_cause_summary` | Month × city × cause | `tasks` |
| `rpt.warehouse_monthly` | Month × warehouse | `items_dispatched`, `items_per_shift`, `stockout_events`, `loader_shifts`, `trips`, `late_dispatch_trips` |
| `rpt.rider_productivity` | Month × city × employment | `riders`, `on_duty_hours`, `task_hours`, `idle_pct`, `completed_tasks`, `tasks_per_hour` |
| `rpt.vehicle_utilisation` | Month × city × owner | `trips`, `tasks_per_trip`, `km_total`, `loaded_km_pct`, `km_per_task` |
| `rpt.items_handled` | Month × city | Items dispatched and returned, used to share warehouse costs between cities |
| `rpt.cost_monthly` | Month × city × cost head × vendor | `amount`, billed basis: own fuel, own van lease and maintenance, 3PL invoices, own and contract riders, packaging and loaders shared by items handled |
| `rpt.unit_costs` | Month × city | `total_cost`, `fleet_cost`, `rider_cost`, `warehouse_cost`, `cost_per_task`, `fleet_cost_per_trip`, `fleet_cost_per_km`, `warehouse_cost_per_item` |
| `rpt.cost_variance` | Month × city (from February) | `change`, `cost_per_task_change_pct`, `volume_effect` (change in tasks × last month's cost per task), `rate_effect` (change in cost per task × this month's tasks) |
| `rpt.cost_head_variance` | Month × city × cost head | `amount`, `prev_amount`, `change` |
| `rpt.vendor_checks` | One per failed check | `check_code` (A01–A05), `vendor_code`, `invoice_no`, `service_month`, `scope`, `detail`, `amount_at_stake` |
| `rpt.escalation_log` | One per failed check | Check fields plus `vendor_name`, `invoice_date`, `owner`, `action`, `raised_on`, `due_on`, `status` |
| `rpt.leakage` | Month × scope × type | `leakage_type` (excess rider capacity, empty km, vendor overbilling), `amount_inr`, `basis` |
| `rpt.leakage_summary` | One per type | `total_inr`, `per_month_inr` |
| `rpt.fleet_inputs` | One per city (April–June) | `own_vans`, `tpl_vans`, trips per month, `km_per_trip`, `own_trips_per_van_day` |
| `rpt.weekly_volume` | Week × city (full weeks) | `trips`, `completed_tasks`, `avg_trip_hours` |
| `rpt.pilot_inputs` | Month × city (Noida, Gurugram) | `tasks`, `km_loaded`, `km_total`, `km_per_task` |

## Answer key

`data/answer_key/expected_findings.csv` lists the planted findings (8 vendor amounts, 6 operational signals). Only the tests read it.
