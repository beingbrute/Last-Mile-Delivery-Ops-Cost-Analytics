"""
Print the analysis from the reporting views, one topic at a time.

Usage:
    python src/show.py ops            --port 5432   # on-time, failures, cancellations, SLA, first-attempt success
    python src/show.py causes         --port 5432   # root causes of late, failed and cancelled tasks
    python src/show.py productivity   --port 5432   # riders, vehicles, warehouse throughput
    python src/show.py costs          --port 5432   # unit costs, cost-to-serve, month-on-month variance
    python src/show.py vendors        --port 5432   # vendor checks A01-A05 and the escalation log
    python src/show.py leakage        --port 5432   # leakage sized in INR
"""
import argparse

from db import add_connection_args, connect

QUERIES = {
    "ops": [
        ("Monthly performance by city",
         """SELECT city_code, month, completed, on_time_pct, failure_pct, cancellation_pct,
                   round(100.0 * sla_breaches / completed, 1) AS sla_breach_pct, first_attempt_success_pct, avg_tat_hours
            FROM rpt.monthly_ops ORDER BY city_code, month"""),
    ],
    "causes": [
        ("Root causes: tasks late, failed or cancelled, by month (all cities)",
         """SELECT root_cause, """ + ", ".join(
             f"SUM(tasks) FILTER (WHERE month = '2025-0{m}') AS \"2025-0{m}\"" for m in range(1, 7)) + """
            FROM rpt.root_cause_summary GROUP BY root_cause ORDER BY SUM(tasks) DESC"""),
        ("Warehouse: stock-outs and trips that left after their slot started",
         """SELECT warehouse_code, month, items_per_shift, stockout_events, trips, late_dispatch_trips
            FROM rpt.warehouse_monthly ORDER BY warehouse_code, month"""),
        ("Bengaluru: failures by slot start hour, before and from May",
         """SELECT extract(hour FROM f.slot_start)::INT AS slot_hour,
                   round(100.0 * COUNT(*) FILTER (WHERE f.status = 'Failed' AND f.month < '2025-05')
                         / NULLIF(COUNT(*) FILTER (WHERE f.status <> 'Cancelled' AND f.month < '2025-05'), 0), 1) AS fail_pct_jan_apr,
                   round(100.0 * COUNT(*) FILTER (WHERE f.status = 'Failed' AND f.month >= '2025-05')
                         / NULLIF(COUNT(*) FILTER (WHERE f.status <> 'Cancelled' AND f.month >= '2025-05'), 0), 1) AS fail_pct_may_jun,
                   COUNT(*) FILTER (WHERE f.month >= '2025-05') AS attempts_may_jun
            FROM rpt.task_facts f WHERE f.city_code = 'BLR' GROUP BY 1 ORDER BY 1"""),
    ],
    "productivity": [
        ("Riders: idle share and completed tasks per on-duty hour",
         """SELECT city_code, month, SUM(riders) AS riders, round(100.0 * (1 - SUM(task_hours) / SUM(on_duty_hours)), 1) AS idle_pct,
                   round(SUM(completed_tasks) / SUM(on_duty_hours), 2) AS tasks_per_hour
            FROM rpt.rider_productivity GROUP BY city_code, month ORDER BY city_code, month"""),
        ("Vehicles: loaded share of km and km per task (Noida zone Z2 and the June pilot stand out)",
         """SELECT city_code, month, SUM(trips) AS trips, round(100.0 * SUM(km_total * loaded_km_pct / 100) / SUM(km_total), 1) AS loaded_km_pct,
                   round(SUM(km_per_task * tasks) / SUM(tasks), 2) AS km_per_task
            FROM rpt.vehicle_utilisation GROUP BY city_code, month ORDER BY city_code, month"""),
        ("Noida empty-km share by zone",
         """SELECT month, round(100 * AVG(empty_share) FILTER (WHERE zone = 'Z1'), 1) AS z1,
                   round(100 * AVG(empty_share) FILTER (WHERE zone = 'Z2'), 1) AS z2,
                   round(100 * AVG(empty_share) FILTER (WHERE zone = 'Z3'), 1) AS z3
            FROM rpt.trip_facts WHERE city_code = 'NOI' GROUP BY month ORDER BY month"""),
    ],
    "costs": [
        ("Unit costs and city cost-to-serve (INR)",
         """SELECT city_code, month, completed_tasks, total_cost, cost_per_task, fleet_cost_per_trip, fleet_cost_per_km,
                   warehouse_cost_per_item FROM rpt.unit_costs ORDER BY city_code, month"""),
        ("Cost per task, month on month: volume effect vs rate effect (INR)",
         """SELECT city_code, month, cost_per_task, cost_per_task_change_pct, volume_effect, rate_effect
            FROM rpt.cost_variance ORDER BY city_code, month"""),
        ("Biggest cost-head changes month on month (INR, above 20,000)",
         """SELECT month, city_code, cost_head, prev_amount, amount, change FROM rpt.cost_head_variance
            WHERE abs(change) > 20000 ORDER BY month, abs(change) DESC"""),
        ("Own-fleet fuel cost per km",
         """SELECT month, round(SUM(amount) / (SELECT SUM(km_total) FROM rpt.trip_facts t WHERE t.owner = 'Own' AND t.month = c.month), 2) AS fuel_per_km
            FROM rpt.cost_monthly c WHERE cost_head = 'Own fleet: fuel' GROUP BY month ORDER BY month"""),
    ],
    "vendors": [
        ("Vendor checks A01-A05",
         "SELECT check_code, vendor_code, invoice_no, service_month, scope, detail, amount_at_stake FROM rpt.vendor_checks ORDER BY service_month, check_code"),
        ("Escalation log",
         "SELECT escalation_id, check_code, vendor_name, invoice_no, amount_at_stake, owner, action, raised_on, due_on, status FROM rpt.escalation_log"),
    ],
    "leakage": [
        ("Leakage summary, January to June 2025 (INR)", "SELECT * FROM rpt.leakage_summary"),
        ("Leakage by month and scope (INR, above 5,000)",
         "SELECT month, scope, leakage_type, amount_inr, basis FROM rpt.leakage WHERE amount_inr > 5000 ORDER BY month, amount_inr DESC"),
    ],
}


def print_table(cur, title, sql):
    cur.execute(sql)
    cols = [d[0] for d in cur.description]
    rows = [["" if v is None else str(v) for v in r] for r in cur.fetchall()]
    widths = [max(len(c), *(len(r[i]) for r in rows)) if rows else len(c) for i, c in enumerate(cols)]
    print(f"\n{title}")
    print("  " + "  ".join(c.ljust(w) for c, w in zip(cols, widths)))
    for r in rows:
        print("  " + "  ".join(v.ljust(w) for v, w in zip(r, widths)))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("topic", choices=QUERIES)
    add_connection_args(p)
    args = p.parse_args()
    con = connect(args)
    with con, con.cursor() as cur:
        for title, sql in QUERIES[args.topic]:
            print_table(cur, title, sql)
    con.close()


if __name__ == "__main__":
    main()
