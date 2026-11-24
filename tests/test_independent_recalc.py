"""Recalculates the main results in pandas straight from the generated CSV files (data/raw),
without using any SQL view, and compares them with the views. A mistake in a view's logic
would have to be made twice, in two languages, to pass."""
import pandas as pd
import pytest

from conftest import raw


@pytest.fixture(scope="module")
def tasks():
    t = raw("ops/tasks.csv", parse_dates=["service_date", "completed_at"])
    o = raw("ops/orders.csv")
    t = t.merge(o, on="order_id", how="left", validate="many_to_one")
    t["month"] = t.service_date.dt.strftime("%Y-%m")
    slot_end = t.service_date + pd.to_timedelta(t.slot_start_hour + 2, unit="h")
    t["on_time"] = (t.status == "Completed") & (t.completed_at <= slot_end)
    return t


@pytest.fixture(scope="module")
def trips():
    tr = raw("ops/trips.csv", parse_dates=["service_date"])
    v = raw("reference/vehicles.csv")[["vehicle_id", "owner"]]
    tr = tr.merge(v, on="vehicle_id", how="left", validate="many_to_one")
    tr["month"] = tr.service_date.dt.strftime("%Y-%m")
    tr["km_total"] = tr.km_loaded + tr.km_empty
    return tr


def test_monthly_on_time_failure_and_cancellation_rates(tasks, query):
    g = tasks.groupby(["month", "city_code"])
    mine = pd.DataFrame({
        "on_time_pct": (100 * g.on_time.sum() / g.status.apply(lambda s: (s == "Completed").sum())).round(1),
        "failure_pct": (100 * g.status.apply(lambda s: (s == "Failed").sum())
                        / g.status.apply(lambda s: (s != "Cancelled").sum())).round(1),
        "cancellation_pct": (100 * g.status.apply(lambda s: (s == "Cancelled").sum())
                             / g.attempt.apply(lambda s: (s == 1).sum())).round(1),
    })
    sql = query("SELECT month, city_code, on_time_pct, failure_pct, cancellation_pct FROM rpt.monthly_ops"
                ).set_index(["month", "city_code"])
    pd.testing.assert_frame_equal(mine.sort_index(), sql.sort_index(), check_dtype=False, atol=0.051)


def test_vendor_checks_recalculated_from_documents(trips, query):
    inv = raw("vendor/invoices.csv")
    grn = raw("vendor/grns.csv").groupby("po_no").quantity_received.sum()
    po = raw("vendor/purchase_orders.csv").set_index("po_no").rate
    card = raw("reference/rate_cards.csv").set_index(["vendor_code", "rate_code"]).rate
    found = []

    # A01 three-way match and A05 price above PO
    for r in inv[inv.po_no.notna()].itertuples():
        if r.quantity > grn.get(r.po_no, r.quantity):
            found.append(("A01", r.invoice_no, (r.quantity - grn[r.po_no]) * r.rate))
        if r.rate > po[r.po_no]:
            found.append(("A05", r.invoice_no, (r.rate - po[r.po_no]) * r.quantity))
    # A02 rate card (services without a PO; every rate card in the data runs all year)
    for r in inv[inv.po_no.isna()].itertuples():
        c = card[(r.vendor_code, r.item)]
        if r.rate > c:
            found.append(("A02", r.invoice_no, (r.rate - c) * r.quantity))
    # A03 3PL km and trips billed vs the trip log
    log = trips[trips.owner == "3PL"].groupby(["month", "city_code"]).agg(trips=("trip_id", "count"),
                                                                           km=("km_total", "sum"))
    for r in inv[inv.vendor_code == "V01"].itertuples():
        logged = log.loc[(r.service_month, r.scope), "km" if r.item == "KM" else "trips"]
        if r.quantity > logged + 1e-9:
            found.append(("A03", r.invoice_no, (r.quantity - logged) * card[("V01", r.item)]))
    # A04 duplicate: same vendor, month, scope, lines and amount under a later invoice number
    tot = (inv.assign(line=inv.item + ":" + inv.quantity.astype(str))
              .groupby(["invoice_no", "vendor_code", "service_month", "scope"])
              .agg(amount=("amount", "sum"), lines=("line", lambda s: ",".join(sorted(s))), date=("invoice_date", "min"))
              .reset_index().sort_values(["date", "invoice_no"]))
    dup = tot.duplicated(["vendor_code", "service_month", "scope", "lines", "amount"])
    found += [("A04", r.invoice_no, r.amount) for r in tot[dup].itertuples()]

    mine = pd.DataFrame(found, columns=["check_code", "invoice_no", "amount"]).round(2)
    sql = query("SELECT check_code, invoice_no, amount_at_stake AS amount FROM rpt.vendor_checks")
    key = ["check_code", "invoice_no"]
    pd.testing.assert_frame_equal(mine.sort_values(key).reset_index(drop=True),
                                  sql.sort_values(key).reset_index(drop=True), check_dtype=False, atol=0.01)


def test_rider_and_fuel_costs_recalculated(trips, query):
    p = raw("reference/cost_parameters.csv").set_index("parameter").value
    riders = raw("reference/riders.csv")
    shifts = raw("ops/rider_shifts.csv", parse_dates=["service_date"])
    fuel = raw("reference/fuel_rates.csv").set_index("month").diesel_per_litre
    months = sorted(trips.month.unique())

    own = [(m, r.city_code, p["own_rider_salary_month"]) for m in months
           for r in riders[riders.employment == "Own"].itertuples() if r.active_from[:7] <= m <= r.active_to[:7]]
    own = pd.DataFrame(own, columns=["month", "city_code", "amount"]).groupby(["month", "city_code"]).amount.sum()

    s = shifts.merge(riders[["rider_id", "employment"]], on="rider_id")
    s = s[s.employment == "Contract"].assign(month=s.service_date.dt.strftime("%Y-%m"))
    contract = s.groupby(["month", "city_code"]).on_duty_hours.sum() * p["contract_rider_per_hour"]

    km = trips[trips.owner == "Own"].groupby(["month", "city_code"]).km_total.sum()
    fuel_cost = km * p["diesel_litres_per_km"] * km.index.get_level_values("month").map(fuel).values

    sql = query("SELECT month, city_code, cost_head, amount FROM rpt.cost_monthly").set_index(["month", "city_code"])
    for head, mine in [("Riders: own", own), ("Riders: contract", contract), ("Own fleet: fuel", fuel_cost)]:
        got = sql[sql.cost_head == head].amount.sort_index()
        assert got.to_dict() == pytest.approx(mine.round(2).sort_index().to_dict(), abs=0.01), head


def test_pilot_effect_recalculated(trips):
    t = trips[trips.city_code.isin(["NOI", "GGN"])].assign(after=trips.month == "2025-06")
    sums = t.groupby(["city_code", "after"])[["km_loaded", "tasks"]].sum()
    k = sums.km_loaded / sums.tasks
    effect = (k[("NOI", True)] - k[("NOI", False)]) - (k[("GGN", True)] - k[("GGN", False)])
    assert effect == pytest.approx(-0.643, abs=0.0005)
    june_tasks = t[(t.city_code == "NOI") & t.after].tasks.sum()
    assert round(-effect * june_tasks) == 1786
