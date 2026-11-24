-- =====================================================================
-- 06  Inputs for the Excel cost model, forecast and pilot measurement
-- =====================================================================

-- Fleet economics per city, April to June (after the diesel revision)
CREATE OR REPLACE VIEW rpt.fleet_inputs AS
WITH t AS (
    SELECT city_code, owner, COUNT(*) AS trips, SUM(km_total) AS km, COUNT(DISTINCT service_date) AS days
    FROM rpt.trip_facts WHERE month BETWEEN '2025-04' AND '2025-06' GROUP BY city_code, owner
), v AS (
    SELECT city_code, COUNT(*) FILTER (WHERE owner = 'Own') AS own_vans, COUNT(*) FILTER (WHERE owner = '3PL') AS tpl_vans
    FROM ref.vehicles GROUP BY city_code
)
SELECT v.city_code, v.own_vans, v.tpl_vans,
       round(o.trips / 3.0, 1) AS own_trips_per_month, round(p.trips / 3.0, 1) AS tpl_trips_per_month,
       round((o.km + p.km) / (o.trips + p.trips), 2) AS km_per_trip,
       round(o.trips::NUMERIC / v.own_vans / o.days, 2) AS own_trips_per_van_day,
       o.days AS days_observed
FROM v JOIN t o ON o.city_code = v.city_code AND o.owner = 'Own'
       JOIN t p ON p.city_code = v.city_code AND p.owner = '3PL';

-- Weekly completed tasks and trips per city (full weeks, Monday start)
CREATE OR REPLACE VIEW rpt.weekly_volume AS
SELECT date_trunc('week', service_date)::DATE AS week_start, city_code,
       COUNT(*) AS trips, SUM(completed) AS completed_tasks, round(AVG(trip_hours), 2) AS avg_trip_hours
FROM rpt.trip_facts
WHERE date_trunc('week', service_date) >= DATE '2025-01-06' AND date_trunc('week', service_date) <= DATE '2025-06-23'
GROUP BY 1, 2;

-- Km per task by city and month, for the route pilot (Noida from June; Gurugram as control)
CREATE OR REPLACE VIEW rpt.pilot_inputs AS
SELECT month, city_code, SUM(tasks) AS tasks, SUM(km_loaded) AS km_loaded, SUM(km_total) AS km_total,
       round(SUM(km_loaded) / SUM(tasks), 3) AS km_per_task
FROM rpt.trip_facts WHERE city_code IN ('NOI', 'GGN') GROUP BY month, city_code;
