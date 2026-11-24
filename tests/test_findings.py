"""Every planted problem in the answer key (data/answer_key/expected_findings.csv) is found by the SQL views."""
import pandas as pd
import pytest

from conftest import ROOT

KEY = pd.read_csv(ROOT / "data" / "answer_key" / "expected_findings.csv")
VENDOR_KEY = KEY[KEY.check_code.str.startswith("A")]


@pytest.mark.parametrize("row", VENDOR_KEY.to_dict("records"),
                         ids=[f"{r.check_code}-{r.month}-{r.scope}" for r in VENDOR_KEY.itertuples()])
def test_vendor_finding_found_with_amount(query, row):
    found = query("SELECT amount_at_stake FROM rpt.vendor_checks "
                  "WHERE check_code = %s AND service_month = %s AND vendor_code = %s AND scope = %s",
                  (row["check_code"], row["month"], row["vendor_code"], row["scope"]))
    assert len(found) == 1, f"expected one {row['check_code']} finding"
    assert found.amount_at_stake[0] == pytest.approx(row["amount_inr"], abs=0.01)


def test_no_vendor_finding_outside_the_answer_key(one):
    assert one("SELECT COUNT(*) FROM rpt.vendor_checks") == len(VENDOR_KEY)


def test_every_finding_is_escalated_with_owner_and_due_date(one):
    assert one("SELECT COUNT(*) FROM rpt.escalation_log") == len(VENDOR_KEY)
    assert one("SELECT COUNT(*) FROM rpt.escalation_log WHERE owner IS NULL OR due_on <= raised_on") == 0
    assert float(one("SELECT SUM(amount_at_stake) FROM rpt.escalation_log")) == pytest.approx(598347.80, abs=0.01)


def test_stockout_late_dispatches_only_in_february_at_wh_ncr(query):
    df = query("SELECT month, city_code, SUM(tasks) AS tasks FROM rpt.root_cause_summary "
               "WHERE root_cause IN ('Late: left the warehouse after the slot started', 'Cancelled: Out of stock') "
               "GROUP BY 1, 2")
    assert set(df.month) == {"2025-02"}
    assert set(df.city_code) == {"NOI", "GGN"}
    assert df.tasks.sum() == 786 + 130


def test_noida_z2_empty_km_doubles_in_march(query):
    df = query("SELECT month, SUM(km_empty) / COUNT(*) AS empty_km_per_trip, "
               "SUM(km_empty) / SUM(km_loaded + km_empty) AS empty_share FROM rpt.trip_facts "
               "WHERE city_code = 'NOI' AND zone = 'Z2' GROUP BY month").set_index("month")
    other = df.drop("2025-03")
    assert df.empty_km_per_trip["2025-03"] > 1.8 * other.empty_km_per_trip.mean()
    assert df.empty_share["2025-03"] > 0.22 > other.empty_share.max(), "only March is above the leakage threshold"


def test_diesel_raises_fuel_cost_per_km_but_barely_moves_cost_per_task(query):
    df = query("SELECT CASE WHEN c.month < '2025-04' THEN 'before' ELSE 'after' END AS period, "
               "SUM(c.amount) FILTER (WHERE c.cost_head = 'Own fleet: fuel') AS fuel, "
               "SUM(c.amount) AS total FROM rpt.cost_monthly c GROUP BY 1").set_index("period")
    km = query("SELECT CASE WHEN month < '2025-04' THEN 'before' ELSE 'after' END AS period, "
               "SUM(km_total) AS km, SUM(completed) AS tasks FROM rpt.trip_facts WHERE owner = 'Own' GROUP BY 1"
               ).set_index("period")
    fuel_per_km = df.fuel / km.km
    assert fuel_per_km["after"] / fuel_per_km["before"] - 1 == pytest.approx(101 / 92 - 1, abs=0.005)
    fuel_share = df.fuel["after"] / df.total["after"]
    assert fuel_share < 0.15, "fuel is a small share of cost, so the price change cannot move cost per task much"


def test_gurugram_extra_contract_riders_idle_in_april_and_may(query):
    df = query("SELECT month, SUM(riders) AS riders, "
               "100.0 * (1 - SUM(task_hours) / SUM(on_duty_hours)) AS idle_pct "
               "FROM rpt.rider_productivity WHERE city_code = 'GGN' GROUP BY month").set_index("month")
    assert (df.loc[["2025-04", "2025-05"], "riders"] == 9).all()
    assert (df.loc[["2025-04", "2025-05"], "idle_pct"] > 25).all()
    assert (df.drop(["2025-04", "2025-05"]).idle_pct < 15).all()


def test_bengaluru_failures_jump_after_early_slots(query):
    df = query("SELECT month, failure_pct FROM rpt.monthly_ops WHERE city_code = 'BLR'").set_index("month").failure_pct
    before = df[df.index < "2025-05"]
    after = df[df.index >= "2025-05"]
    assert after.min() > 2 * before.max()


def test_noida_pilot_cuts_km_per_task_and_gurugram_does_not(query):
    df = query("SELECT city_code, month >= '2025-06' AS pilot, SUM(km_loaded) / SUM(tasks) AS km_per_task "
               "FROM rpt.pilot_inputs GROUP BY 1, 2")
    k = df.set_index(["city_code", "pilot"]).km_per_task
    noida = k[("NOI", True)] / k[("NOI", False)] - 1
    gurugram = k[("GGN", True)] / k[("GGN", False)] - 1
    assert noida < -0.08
    assert abs(gurugram) < 0.03
