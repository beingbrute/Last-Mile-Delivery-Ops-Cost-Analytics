"""
Export the reporting views to CSV (reporting/) for Excel, Google Sheets and Power BI.

Usage:
    python src/export_reporting.py --port 5432
"""
import argparse
import csv
from pathlib import Path

from db import add_connection_args, connect

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reporting"

VIEWS = ["monthly_ops", "daily_ops", "root_cause_summary", "warehouse_monthly", "rider_productivity",
         "vehicle_utilisation", "cost_monthly", "unit_costs", "cost_variance", "cost_head_variance",
         "vendor_checks", "escalation_log", "leakage", "leakage_summary",
         "fleet_inputs", "weekly_volume", "pilot_inputs"]


def main():
    p = argparse.ArgumentParser()
    add_connection_args(p)
    args = p.parse_args()
    OUT.mkdir(exist_ok=True)
    con = connect(args)
    with con, con.cursor() as cur:
        for view in VIEWS:
            cur.execute(f"SELECT * FROM rpt.{view}")
            cols = [d[0] for d in cur.description]
            rows = cur.fetchall()
            with open(OUT / f"{view}.csv", "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(cols)
                w.writerows(rows)
            print(f"  {view:<22} {len(rows):>6} rows")
    con.close()
    print("Exported to reporting/")


if __name__ == "__main__":
    main()
