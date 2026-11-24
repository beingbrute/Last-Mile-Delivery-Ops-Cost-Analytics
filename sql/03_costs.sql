-- =====================================================================
-- 03  Costs: monthly cost by city and cost head, unit costs, month-on-month variance
-- Costs are on a billed basis (what the company was charged). The vendor checks (04) show
-- which part of the billed amount should not have been charged.
-- =====================================================================

CREATE OR REPLACE FUNCTION rpt.param(p_name TEXT) RETURNS NUMERIC LANGUAGE sql STABLE AS $$
    SELECT value FROM ref.cost_parameters WHERE parameter = p_name
$$;

-- Items handled per city and month (deliveries sent out + pickups brought back): used to share warehouse costs
CREATE OR REPLACE VIEW rpt.items_handled AS
SELECT month, city_code,
       SUM(items) FILTER (WHERE order_type = 'Delivery' AND trip_id IS NOT NULL) AS items_dispatched,
       SUM(items) FILTER (WHERE order_type = 'Pickup' AND status = 'Completed')  AS items_returned,
       COALESCE(SUM(items) FILTER (WHERE order_type = 'Delivery' AND trip_id IS NOT NULL), 0)
     + COALESCE(SUM(items) FILTER (WHERE order_type = 'Pickup' AND status = 'Completed'), 0) AS items_handled
FROM rpt.task_facts GROUP BY month, city_code;

CREATE OR REPLACE VIEW rpt.cost_monthly AS
WITH months AS (SELECT DISTINCT month FROM rpt.task_facts),
fuel AS (                                   -- own vans: km x litres per km x diesel price of the month
    SELECT t.month, t.city_code, 'Own fleet: fuel' AS cost_head, ''::TEXT AS vendor_code,
           SUM(t.km_total) * rpt.param('diesel_litres_per_km') * MAX(f.diesel_per_litre) AS amount
    FROM rpt.trip_facts t JOIN ref.fuel_rates f ON f.month = t.month
    WHERE t.owner = 'Own' GROUP BY t.month, t.city_code
),
vans AS (                                   -- own vans: lease and maintenance
    SELECT m.month, v.city_code, 'Own fleet: lease and maintenance', '', COUNT(*) * rpt.param('own_van_fixed_month')
    FROM months m CROSS JOIN ref.vehicles v WHERE v.owner = 'Own' GROUP BY m.month, v.city_code
),
tpl AS (                                    -- 3PL vans: as invoiced, per city
    SELECT service_month, scope, '3PL fleet', vendor_code, SUM(amount)
    FROM vnd.invoices WHERE vendor_code = 'V01' GROUP BY service_month, scope, vendor_code
),
own_riders AS (
    SELECT m.month, r.city_code, 'Riders: own', '', COUNT(*) * rpt.param('own_rider_salary_month')
    FROM months m JOIN ref.riders r
      ON r.employment = 'Own' AND to_char(r.active_from, 'YYYY-MM') <= m.month AND to_char(r.active_to, 'YYYY-MM') >= m.month
    GROUP BY m.month, r.city_code
),
contract_riders AS (
    SELECT to_char(s.service_date, 'YYYY-MM'), s.city_code, 'Riders: contract', '',
           SUM(s.on_duty_hours) * rpt.param('contract_rider_per_hour')
    FROM ops.rider_shifts s JOIN ref.riders r USING (rider_id) WHERE r.employment = 'Contract' GROUP BY 1, 2
),
wh_bills AS (                               -- packaging (V02) and loaders (V03), as invoiced per warehouse
    SELECT service_month AS month, scope AS warehouse_code, vendor_code,
           CASE vendor_code WHEN 'V02' THEN 'Packaging' ELSE 'Warehouse loaders' END AS cost_head, SUM(amount) AS amount
    FROM vnd.invoices WHERE vendor_code IN ('V02', 'V03') GROUP BY 1, 2, 3
),
wh_share AS (                               -- each city's share of its warehouse's items handled
    SELECT h.month, h.city_code, c.warehouse_code,
           h.items_handled::NUMERIC / SUM(h.items_handled) OVER (PARTITION BY h.month, c.warehouse_code) AS share
    FROM rpt.items_handled h JOIN ref.cities c USING (city_code)
),
wh AS (
    SELECT s.month, s.city_code, b.cost_head, b.vendor_code, b.amount * s.share
    FROM wh_share s JOIN wh_bills b USING (month, warehouse_code)
)
SELECT month, city_code, cost_head, NULLIF(vendor_code, '') AS vendor_code, round(amount, 2) AS amount
FROM (SELECT * FROM fuel UNION ALL SELECT * FROM vans UNION ALL SELECT * FROM tpl
      UNION ALL SELECT * FROM own_riders UNION ALL SELECT * FROM contract_riders UNION ALL SELECT * FROM wh) x(month, city_code, cost_head, vendor_code, amount);

-- Unit costs and city cost-to-serve
CREATE OR REPLACE VIEW rpt.unit_costs AS
WITH c AS (
    SELECT month, city_code, SUM(amount) AS total_cost,
           SUM(amount) FILTER (WHERE cost_head LIKE 'Own fleet%' OR cost_head = '3PL fleet') AS fleet_cost,
           SUM(amount) FILTER (WHERE cost_head LIKE 'Riders%') AS rider_cost,
           SUM(amount) FILTER (WHERE cost_head IN ('Packaging', 'Warehouse loaders')) AS warehouse_cost
    FROM rpt.cost_monthly GROUP BY month, city_code
), v AS (
    SELECT month, city_code, COUNT(*) AS trips, SUM(completed) AS completed_tasks, SUM(km_total) AS km_total
    FROM rpt.trip_facts GROUP BY month, city_code
)
SELECT c.month, c.city_code, v.completed_tasks, v.trips, h.items_handled, v.km_total,
       round(c.total_cost, 2) AS total_cost, round(c.fleet_cost, 2) AS fleet_cost,
       round(c.rider_cost, 2) AS rider_cost, round(c.warehouse_cost, 2) AS warehouse_cost,
       round(c.total_cost / v.completed_tasks, 2)    AS cost_per_task,          -- city cost-to-serve
       round(c.fleet_cost / v.trips, 2)              AS fleet_cost_per_trip,
       round(c.fleet_cost / v.km_total, 2)           AS fleet_cost_per_km,
       round(c.warehouse_cost / h.items_handled, 2)  AS warehouse_cost_per_item
FROM c JOIN v USING (month, city_code) JOIN rpt.items_handled h USING (month, city_code);

-- Month-on-month change in cost per task, split into what moved it:
--   volume effect: change in completed tasks at last month's cost per task
--   rate effect:   change in cost per task at this month's volume
-- plus the change by cost head, for the commentary.
CREATE OR REPLACE VIEW rpt.cost_variance AS
SELECT u.month, u.city_code, u.total_cost, p.total_cost AS prev_total_cost,
       round(u.total_cost - p.total_cost, 2) AS change,
       u.cost_per_task, p.cost_per_task AS prev_cost_per_task,
       round(100.0 * (u.cost_per_task - p.cost_per_task) / p.cost_per_task, 1) AS cost_per_task_change_pct,
       round((u.completed_tasks - p.completed_tasks) * p.cost_per_task, 2) AS volume_effect,
       round((u.cost_per_task - p.cost_per_task) * u.completed_tasks, 2) AS rate_effect
FROM rpt.unit_costs u
JOIN rpt.unit_costs p ON p.city_code = u.city_code
                     AND p.month = to_char(to_date(u.month || '-01', 'YYYY-MM-DD') - INTERVAL '1 month', 'YYYY-MM');

CREATE OR REPLACE VIEW rpt.cost_head_variance AS
SELECT c.month, c.city_code, c.cost_head, c.amount, p.amount AS prev_amount, round(c.amount - p.amount, 2) AS change
FROM (SELECT month, city_code, cost_head, SUM(amount) AS amount FROM rpt.cost_monthly GROUP BY 1, 2, 3) c
JOIN (SELECT month, city_code, cost_head, SUM(amount) AS amount FROM rpt.cost_monthly GROUP BY 1, 2, 3) p
  ON p.city_code = c.city_code AND p.cost_head = c.cost_head
 AND p.month = to_char(to_date(c.month || '-01', 'YYYY-MM-DD') - INTERVAL '1 month', 'YYYY-MM');
