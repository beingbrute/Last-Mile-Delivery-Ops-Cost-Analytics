-- =====================================================================
-- 05  Cost leakage: money spent without a matching operational need, sized in INR
-- Targets (operating assumptions, not facts from the data):
--   rider idle share up to 15% of on-duty hours is normal (loading, breaks, waiting for slots)
--   empty (return) km up to 22% of a trip's km is normal
-- =====================================================================

CREATE OR REPLACE VIEW rpt.leakage AS
WITH idle AS (   -- rider hours above the 15% idle allowance, at each rider type's hourly cost
    SELECT to_char(s.service_date, 'YYYY-MM') AS month, s.city_code AS scope,
           'Excess rider capacity (idle above 15%)' AS leakage_type,
           SUM(GREATEST(s.on_duty_hours - s.task_hours - 0.15 * s.on_duty_hours, 0)
               * CASE r.employment WHEN 'Contract' THEN rpt.param('contract_rider_per_hour')
                                   ELSE rpt.param('own_rider_salary_month') / (9 * 30.0) END) AS amount,
           round(SUM(GREATEST(s.on_duty_hours - s.task_hours - 0.15 * s.on_duty_hours, 0)), 1)::TEXT || ' excess rider-hours' AS basis
    FROM ops.rider_shifts s JOIN ref.riders r USING (rider_id) GROUP BY 1, 2
),
empty_km AS (   -- empty km above 22% of the trip, at the cost of a km (fuel for own vans, contract rate for 3PL)
    SELECT t.month, t.city_code, 'Empty return km above 22%',
           SUM(GREATEST(t.km_empty - 0.22 * t.km_total, 0)
               * CASE t.owner WHEN 'Own' THEN rpt.param('diesel_litres_per_km') * f.diesel_per_litre
                              ELSE (SELECT rate FROM ref.rate_cards WHERE vendor_code = 'V01' AND rate_code = 'KM') END),
           round(SUM(GREATEST(t.km_empty - 0.22 * t.km_total, 0)), 0)::TEXT || ' excess empty km'
    FROM rpt.trip_facts t JOIN ref.fuel_rates f USING (month) GROUP BY 1, 2
),
billing AS (    -- overbilling found by the vendor checks
    SELECT service_month, scope, 'Vendor overbilling (' || check_code || ')', SUM(amount_at_stake),
           COUNT(*)::TEXT || ' invoice line(s)'
    FROM rpt.vendor_checks GROUP BY 1, 2, check_code
)
SELECT month, scope, leakage_type, round(amount, 2) AS amount_inr, basis
FROM (SELECT * FROM idle UNION ALL SELECT * FROM empty_km UNION ALL SELECT * FROM billing) x(month, scope, leakage_type, amount, basis)
WHERE amount > 0;

CREATE OR REPLACE VIEW rpt.leakage_summary AS
SELECT leakage_type, SUM(amount_inr) AS total_inr, round(SUM(amount_inr) / 6, 2) AS per_month_inr
FROM rpt.leakage GROUP BY leakage_type ORDER BY total_inr DESC;
