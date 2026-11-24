"""
Create the `lastmile` database, build the schema and load every source file as received.

  1. creates the database if it does not exist
  2. runs sql/01_schema.sql (and the metric and check scripts in sql/ when they exist)
  3. loads data/raw/reference, ops and vendor files with COPY; nothing is changed or corrected here

Usage:
    python src/load_data.py --port 5432
"""
import argparse
import sys
from pathlib import Path

from db import DB_NAME, add_connection_args, connect

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
SQL = ROOT / "sql"

# (table, file, columns) in load order: parents before children
FILES = [
    ("ref.warehouses", "reference/warehouses.csv", None),
    ("ref.cities", "reference/cities.csv", None),
    ("ref.vendors", "reference/vendors.csv", None),
    ("ref.riders", "reference/riders.csv", None),
    ("ref.vehicles", "reference/vehicles.csv", None),
    ("ref.rate_cards", "reference/rate_cards.csv", None),
    ("ref.fuel_rates", "reference/fuel_rates.csv", None),
    ("ref.cost_parameters", "reference/cost_parameters.csv", None),
    ("ops.orders", "ops/orders.csv", None),
    ("ops.trips", "ops/trips.csv", None),
    ("ops.tasks", "ops/tasks.csv", None),
    ("ops.rider_shifts", "ops/rider_shifts.csv", None),
    ("ops.warehouse_shifts", "ops/warehouse_shifts.csv", None),
    ("vnd.purchase_orders", "vendor/purchase_orders.csv", None),
    ("vnd.grns", "vendor/grns.csv", None),
    ("vnd.invoices", "vendor/invoices.csv",
     "invoice_no, vendor_code, invoice_date, service_month, scope, po_no, item, quantity, rate, amount"),
]


def main():
    p = argparse.ArgumentParser()
    add_connection_args(p)
    args = p.parse_args()
    if not (RAW / "ops" / "orders.csv").exists():
        print("ERROR: data/raw not found. Run: python src/generate_data.py")
        sys.exit(2)

    con = connect(args, "postgres")
    con.autocommit = True
    with con.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (DB_NAME,))
        if cur.fetchone() is None:
            cur.execute(f"CREATE DATABASE {DB_NAME}")
            print(f"Created database {DB_NAME}")
    con.close()

    con = connect(args)
    with con, con.cursor() as cur:
        scripts = sorted(SQL.glob("*.sql"))
        for f in scripts:
            cur.execute(f.read_text(encoding="utf-8"))
        for table, name, cols in FILES:
            target = f"{table} ({cols})" if cols else table
            with open(RAW / name, encoding="utf-8") as fh:
                cur.copy_expert(f"COPY {target} FROM STDIN WITH (FORMAT csv, HEADER true)", fh)
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            print(f"  {table:<22} {cur.fetchone()[0]:>7} rows")
        # stored views (materialized) are filled after the data is in, in the order they depend on each other
        cur.execute("""SELECT schemaname || '.' || matviewname FROM pg_matviews
                       WHERE schemaname = 'rpt' ORDER BY CASE matviewname WHEN 'task_facts' THEN 0
                                                                          WHEN 'trip_facts' THEN 1 ELSE 2 END""")
        for (mv,) in cur.fetchall():
            cur.execute(f"REFRESH MATERIALIZED VIEW {mv}")
            print(f"  refreshed {mv}")
    con.close()
    print(f"Ran {len(scripts)} SQL script(s). Done.")


if __name__ == "__main__":
    main()
