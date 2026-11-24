"""The data loaded correctly and the reporting layers agree with each other."""
import pandas as pd
import pytest

from conftest import ROOT, raw

TABLES = {"ops.orders": "ops/orders.csv", "ops.tasks": "ops/tasks.csv", "ops.trips": "ops/trips.csv",
          "ops.rider_shifts": "ops/rider_shifts.csv", "ops.warehouse_shifts": "ops/warehouse_shifts.csv",
          "vnd.invoices": "vendor/invoices.csv", "vnd.grns": "vendor/grns.csv",
          "vnd.purchase_orders": "vendor/purchase_orders.csv"}


@pytest.mark.parametrize("table,path", TABLES.items(), ids=list(TABLES))
def test_every_source_row_loaded(one, table, path):
    assert one(f"SELECT COUNT(*) FROM {table}") == len(raw(path))


def test_task_outcomes_are_consistent(one):
    assert one("SELECT COUNT(*) FROM ops.tasks WHERE status = 'Completed' AND completed_at IS NULL") == 0
    assert one("SELECT COUNT(*) FROM ops.tasks WHERE status <> 'Completed' AND completed_at IS NOT NULL") == 0
    assert one("SELECT COUNT(*) FROM ops.tasks WHERE status = 'Cancelled' AND trip_id IS NOT NULL") == 0
    assert one("SELECT COUNT(*) FROM ops.tasks t LEFT JOIN ops.trips r USING (trip_id) "
               "WHERE t.trip_id IS NOT NULL AND r.trip_id IS NULL") == 0


def test_every_task_not_on_time_has_exactly_one_root_cause(one):
    not_on_time = one("SELECT COUNT(*) FROM rpt.task_facts WHERE NOT on_time")
    assert one("SELECT COUNT(*) FROM rpt.task_root_causes") == not_on_time == 8350
    assert one("SELECT COUNT(*) - COUNT(DISTINCT task_id) FROM rpt.task_root_causes") == 0


def test_trip_task_counts_match_tasks(one):
    assert one("SELECT COUNT(*) FROM ops.trips r JOIN (SELECT trip_id, COUNT(*) AS n FROM ops.tasks "
               "WHERE trip_id IS NOT NULL GROUP BY trip_id) t USING (trip_id) WHERE r.tasks <> t.n") == 0


def test_cost_views_agree(one):
    by_head = one("SELECT SUM(amount) FROM rpt.cost_monthly")
    by_city = one("SELECT SUM(total_cost) FROM rpt.unit_costs")
    assert float(by_head) == pytest.approx(float(by_city), abs=1.0)
    assert float(by_city) == pytest.approx(18308379.33, abs=1.0)


def test_vendor_invoices_fully_charged_to_cities(one):
    """Packaging and loader bills are shared out to cities by items handled: nothing lost or added."""
    billed = one("SELECT SUM(amount) FROM vnd.invoices")
    charged = one("SELECT SUM(amount) FROM rpt.cost_monthly WHERE vendor_code IS NOT NULL")
    assert float(charged) == pytest.approx(float(billed), abs=1.0)


def test_volume_plus_rate_effect_equals_change(query):
    df = query("SELECT * FROM rpt.cost_variance")
    gap = (df.volume_effect + df.rate_effect - df.change).abs()
    # cost per task is rounded to 2 decimals in SQL, so each row can be off by a few rupees
    assert (gap <= 0.005 * (df.total_cost / df.cost_per_task) * 2 + 1).all(), gap.max()


@pytest.mark.parametrize("view", ["monthly_ops", "unit_costs", "vendor_checks", "leakage_summary"])
def test_reporting_csv_matches_the_view(query, view):
    """reporting/*.csv (read by Excel, Google Sheets and the README) is up to date with the database."""
    csv = pd.read_csv(ROOT / "reporting" / f"{view}.csv")
    sql = query(f"SELECT * FROM rpt.{view}")
    key = list(csv.columns[:3])
    a = csv.sort_values(key).reset_index(drop=True)
    b = sql[csv.columns].sort_values(key).reset_index(drop=True)
    pd.testing.assert_frame_equal(a, b, check_dtype=False, atol=0.005)
