-- =====================================================================
-- 02  Operational metrics: tasks, trips, performance, root causes, productivity
-- Metric definitions: docs/design.md section 3. Every report reads these views.
-- =====================================================================

-- task_facts and trip_facts are materialized (stored) because every other view reads them;
-- src/load_data.py refreshes them after loading the data.

-- One row per delivery or pickup attempt, with its slot and outcome
CREATE MATERIALIZED VIEW rpt.task_facts AS
SELECT t.task_id, t.order_id, t.attempt, t.service_date, to_char(t.service_date, 'YYYY-MM') AS month,
       o.city_code, o.zone, o.order_type, o.items, t.status, t.reason, t.trip_id, t.completed_at,
       o.created_at,
       t.service_date + make_interval(hours => o.slot_start_hour)     AS slot_start,
       t.service_date + make_interval(hours => o.slot_start_hour + 2) AS slot_end,
       o.promised_date + make_interval(hours => o.slot_start_hour + 2) AS promised_slot_end,
       (t.status = 'Completed'
        AND t.completed_at <= t.service_date + make_interval(hours => o.slot_start_hour + 2)) AS on_time,
       CASE WHEN t.status = 'Completed'
            THEN round(EXTRACT(EPOCH FROM t.completed_at - o.created_at) / 3600.0, 2) END AS tat_hours
FROM ops.tasks t JOIN ops.orders o USING (order_id)
WITH NO DATA;

-- One row per trip: who, which van, distance, timing, and whether it left the warehouse late
CREATE MATERIALIZED VIEW rpt.trip_facts AS
SELECT tr.trip_id, tr.service_date, to_char(tr.service_date, 'YYYY-MM') AS month, tr.city_code, tr.warehouse_code,
       tr.zone, tr.vehicle_id, v.owner, tr.rider_id, tr.start_at, tr.end_at, tr.tasks,
       tr.km_loaded, tr.km_empty, tr.km_loaded + tr.km_empty AS km_total,
       round(tr.km_empty / NULLIF(tr.km_loaded + tr.km_empty, 0), 4) AS empty_share,
       round(EXTRACT(EPOCH FROM tr.end_at - tr.start_at) / 3600.0, 2) AS trip_hours,
       tr.idle_minutes,
       s.first_slot_start,
       (tr.start_at > s.first_slot_start) AS late_dispatch,
       s.completed
FROM ops.trips tr
JOIN ref.vehicles v USING (vehicle_id)
JOIN (SELECT trip_id, MIN(slot_start) AS first_slot_start,
             COUNT(*) FILTER (WHERE status = 'Completed') AS completed
      FROM rpt.task_facts WHERE trip_id IS NOT NULL GROUP BY trip_id) s USING (trip_id)
WITH NO DATA;

-- Daily performance by city
CREATE OR REPLACE VIEW rpt.daily_ops AS
SELECT service_date, month, city_code,
       COUNT(*)                                             AS attempts,
       COUNT(*) FILTER (WHERE attempt = 1)                  AS first_attempts,
       COUNT(*) FILTER (WHERE status = 'Completed')         AS completed,
       COUNT(*) FILTER (WHERE status = 'Failed')            AS failed,
       COUNT(*) FILTER (WHERE status = 'Cancelled')         AS cancelled,
       COUNT(*) FILTER (WHERE on_time)                      AS on_time,
       COUNT(*) FILTER (WHERE status = 'Completed' AND completed_at > promised_slot_end) AS sla_breaches,
       round(AVG(tat_hours), 2)                             AS avg_tat_hours
FROM rpt.task_facts
GROUP BY service_date, month, city_code;

-- Monthly performance by city (the rates are ratios of the counts, not averages of daily rates)
CREATE OR REPLACE VIEW rpt.monthly_ops AS
WITH first AS (
    SELECT month, city_code,
           round(100.0 * COUNT(*) FILTER (WHERE status = 'Completed') / NULLIF(COUNT(*), 0), 1) AS first_attempt_success_pct
    FROM rpt.task_facts WHERE attempt = 1 AND status <> 'Cancelled' GROUP BY month, city_code
)
SELECT d.month, d.city_code,
       SUM(attempts) AS attempts, SUM(completed) AS completed, SUM(failed) AS failed, SUM(cancelled) AS cancelled,
       round(100.0 * SUM(on_time) / NULLIF(SUM(completed), 0), 1)                AS on_time_pct,
       round(100.0 * SUM(failed) / NULLIF(SUM(attempts) - SUM(cancelled), 0), 1) AS failure_pct,
       round(100.0 * SUM(cancelled) / NULLIF(SUM(first_attempts), 0), 1)        AS cancellation_pct,
       SUM(sla_breaches) AS sla_breaches,
       round(SUM(avg_tat_hours * completed) / NULLIF(SUM(completed), 0), 1)     AS avg_tat_hours,
       MAX(f.first_attempt_success_pct) AS first_attempt_success_pct
FROM rpt.daily_ops d JOIN first f USING (month, city_code)
GROUP BY d.month, d.city_code;

-- Root cause of every task that was late, failed or cancelled
CREATE OR REPLACE VIEW rpt.task_root_causes AS
SELECT f.month, f.city_code, f.zone, f.task_id,
       CASE WHEN f.status = 'Cancelled' THEN 'Cancelled: ' || f.reason
            WHEN f.status = 'Failed'    THEN 'Failed: ' || f.reason
            WHEN tr.late_dispatch       THEN 'Late: left the warehouse after the slot started'
            ELSE 'Late: delay on the route' END AS root_cause
FROM rpt.task_facts f LEFT JOIN rpt.trip_facts tr USING (trip_id)
WHERE f.status IN ('Cancelled', 'Failed') OR (f.status = 'Completed' AND NOT f.on_time);

CREATE OR REPLACE VIEW rpt.root_cause_summary AS
SELECT month, city_code, root_cause, COUNT(*) AS tasks
FROM rpt.task_root_causes GROUP BY month, city_code, root_cause;

-- Warehouse throughput and stock-outs
CREATE OR REPLACE VIEW rpt.warehouse_monthly AS
WITH late AS (
    SELECT month, warehouse_code, COUNT(*) FILTER (WHERE late_dispatch) AS late_dispatch_trips, COUNT(*) AS trips
    FROM rpt.trip_facts GROUP BY month, warehouse_code
)
SELECT to_char(w.service_date, 'YYYY-MM') AS month, w.warehouse_code,
       SUM(w.items_dispatched) AS items_dispatched, SUM(w.items_returned) AS items_returned,
       round(AVG(w.items_dispatched), 1) AS items_per_shift, SUM(w.stockout_events) AS stockout_events,
       SUM(w.loaders) AS loader_shifts, MAX(l.trips) AS trips, MAX(l.late_dispatch_trips) AS late_dispatch_trips
FROM ops.warehouse_shifts w JOIN late l ON l.warehouse_code = w.warehouse_code AND l.month = to_char(w.service_date, 'YYYY-MM')
GROUP BY 1, 2;

-- Rider productivity: completed tasks per on-duty hour and idle share
CREATE OR REPLACE VIEW rpt.rider_productivity AS
WITH hours AS (
    SELECT to_char(s.service_date, 'YYYY-MM') AS month, s.city_code, r.employment,
           COUNT(DISTINCT s.rider_id) AS riders, SUM(s.on_duty_hours) AS on_duty_hours, SUM(s.task_hours) AS task_hours
    FROM ops.rider_shifts s JOIN ref.riders r USING (rider_id)
    GROUP BY 1, 2, 3
), done AS (
    SELECT t.month, t.city_code, r.employment, SUM(t.completed) AS completed
    FROM rpt.trip_facts t JOIN ref.riders r USING (rider_id)
    GROUP BY 1, 2, 3
)
SELECT h.month, h.city_code, h.employment, h.riders, h.on_duty_hours, h.task_hours,
       round(100.0 * (1 - h.task_hours / NULLIF(h.on_duty_hours, 0)), 1) AS idle_pct,
       COALESCE(d.completed, 0) AS completed_tasks,
       round(COALESCE(d.completed, 0) / NULLIF(h.on_duty_hours, 0), 2) AS tasks_per_hour
FROM hours h LEFT JOIN done d USING (month, city_code, employment);

-- Vehicle utilisation: loaded share of km and tasks per trip, own vs 3PL
CREATE OR REPLACE VIEW rpt.vehicle_utilisation AS
SELECT month, city_code, owner, COUNT(*) AS trips, SUM(tasks) AS tasks,
       round(AVG(tasks), 2) AS tasks_per_trip, SUM(km_total) AS km_total,
       round(100.0 * SUM(km_loaded) / NULLIF(SUM(km_total), 0), 1) AS loaded_km_pct,
       round(SUM(km_loaded) / NULLIF(SUM(tasks), 0), 2) AS km_per_task
FROM rpt.trip_facts
GROUP BY month, city_code, owner;
