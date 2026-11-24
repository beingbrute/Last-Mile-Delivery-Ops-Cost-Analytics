-- =====================================================================
-- 01  Schema: reference data, operations, vendor documents, reporting
-- Database: lastmile   (Kestrel Rentals, synthetic data, Jan-Jun 2025)
-- =====================================================================

DROP SCHEMA IF EXISTS rpt CASCADE;
DROP SCHEMA IF EXISTS vnd CASCADE;
DROP SCHEMA IF EXISTS ops CASCADE;
DROP SCHEMA IF EXISTS ref CASCADE;

CREATE SCHEMA ref;   -- cities, warehouses, riders, vehicles, vendors, rate cards, fuel, cost parameters
CREATE SCHEMA ops;   -- orders, task attempts, trips, rider and warehouse shifts
CREATE SCHEMA vnd;   -- purchase orders, goods received notes, vendor invoices
CREATE SCHEMA rpt;   -- metric views for Excel, Google Sheets and Power BI

-- ---------------------------------------------------------------- reference
CREATE TABLE ref.warehouses (
    warehouse_code     TEXT PRIMARY KEY,
    warehouse_name     TEXT NOT NULL,
    loaders_per_shift  INT  NOT NULL
);

CREATE TABLE ref.cities (
    city_code       TEXT PRIMARY KEY,
    city_name       TEXT NOT NULL,
    warehouse_code  TEXT NOT NULL REFERENCES ref.warehouses
);

CREATE TABLE ref.vendors (
    vendor_code  TEXT PRIMARY KEY,
    vendor_name  TEXT NOT NULL,
    service      TEXT NOT NULL
);

CREATE TABLE ref.riders (
    rider_id     TEXT PRIMARY KEY,
    city_code    TEXT NOT NULL REFERENCES ref.cities,
    employment   TEXT NOT NULL CHECK (employment IN ('Own', 'Contract')),
    active_from  DATE NOT NULL,
    active_to    DATE NOT NULL
);

CREATE TABLE ref.vehicles (
    vehicle_id   TEXT PRIMARY KEY,
    city_code    TEXT NOT NULL REFERENCES ref.cities,
    owner        TEXT NOT NULL CHECK (owner IN ('Own', '3PL')),
    vendor_code  TEXT REFERENCES ref.vendors,
    fuel         TEXT NOT NULL
);

CREATE TABLE ref.rate_cards (
    vendor_code  TEXT    NOT NULL REFERENCES ref.vendors,
    rate_code    TEXT    NOT NULL,
    description  TEXT    NOT NULL,
    rate         NUMERIC NOT NULL,
    valid_from   DATE    NOT NULL,
    valid_to     DATE    NOT NULL,
    PRIMARY KEY (vendor_code, rate_code, valid_from)
);

CREATE TABLE ref.fuel_rates (
    month             TEXT PRIMARY KEY,
    diesel_per_litre  NUMERIC NOT NULL
);

CREATE TABLE ref.cost_parameters (
    parameter  TEXT PRIMARY KEY,
    value      NUMERIC NOT NULL
);

-- ---------------------------------------------------------------- operations
CREATE TABLE ops.orders (
    order_id         TEXT PRIMARY KEY,
    order_type       TEXT      NOT NULL CHECK (order_type IN ('Delivery', 'Pickup')),
    city_code        TEXT      NOT NULL REFERENCES ref.cities,
    zone             TEXT      NOT NULL,
    items            INT       NOT NULL,
    created_at       TIMESTAMP NOT NULL,
    promised_date    DATE      NOT NULL,
    slot_start_hour  INT       NOT NULL     -- 2-hour slot
);

CREATE TABLE ops.trips (
    trip_id         TEXT PRIMARY KEY,
    service_date    DATE      NOT NULL,
    city_code       TEXT      NOT NULL REFERENCES ref.cities,
    warehouse_code  TEXT      NOT NULL REFERENCES ref.warehouses,
    zone            TEXT      NOT NULL,
    vehicle_id      TEXT      NOT NULL REFERENCES ref.vehicles,
    rider_id        TEXT      NOT NULL REFERENCES ref.riders,
    start_at        TIMESTAMP NOT NULL,
    end_at          TIMESTAMP NOT NULL,
    tasks           INT       NOT NULL,
    km_loaded       NUMERIC   NOT NULL,
    km_empty        NUMERIC   NOT NULL,
    idle_minutes    INT       NOT NULL
);

CREATE TABLE ops.tasks (
    task_id       TEXT PRIMARY KEY,
    order_id      TEXT NOT NULL REFERENCES ops.orders,
    attempt       INT  NOT NULL,
    service_date  DATE NOT NULL,
    trip_id       TEXT REFERENCES ops.trips,          -- empty if cancelled before dispatch
    status        TEXT NOT NULL CHECK (status IN ('Completed', 'Failed', 'Cancelled')),
    reason        TEXT,
    completed_at  TIMESTAMP
);

CREATE TABLE ops.rider_shifts (
    service_date   DATE    NOT NULL,
    rider_id       TEXT    NOT NULL REFERENCES ref.riders,
    city_code      TEXT    NOT NULL REFERENCES ref.cities,
    on_duty_hours  NUMERIC NOT NULL,
    task_hours     NUMERIC NOT NULL,
    PRIMARY KEY (service_date, rider_id)
);

CREATE TABLE ops.warehouse_shifts (
    service_date      DATE NOT NULL,
    warehouse_code    TEXT NOT NULL REFERENCES ref.warehouses,
    shift             TEXT NOT NULL,
    items_dispatched  INT  NOT NULL,
    items_returned    INT  NOT NULL,
    stockout_events   INT  NOT NULL,
    loaders           INT  NOT NULL,
    PRIMARY KEY (service_date, warehouse_code, shift)
);

-- ---------------------------------------------------------------- vendor documents
CREATE TABLE vnd.purchase_orders (
    po_no           TEXT PRIMARY KEY,
    vendor_code     TEXT    NOT NULL REFERENCES ref.vendors,
    warehouse_code  TEXT    NOT NULL REFERENCES ref.warehouses,
    po_date         DATE    NOT NULL,
    item            TEXT    NOT NULL,
    quantity        NUMERIC NOT NULL,
    rate            NUMERIC NOT NULL,
    amount          NUMERIC(18,2) NOT NULL
);

CREATE TABLE vnd.grns (
    grn_no             TEXT PRIMARY KEY,
    po_no              TEXT    NOT NULL REFERENCES vnd.purchase_orders,
    vendor_code        TEXT    NOT NULL REFERENCES ref.vendors,
    warehouse_code     TEXT    NOT NULL REFERENCES ref.warehouses,
    grn_date           DATE    NOT NULL,
    item               TEXT    NOT NULL,
    quantity_received  NUMERIC NOT NULL
);

CREATE TABLE vnd.invoices (
    line_id        SERIAL PRIMARY KEY,
    invoice_no     TEXT    NOT NULL,
    vendor_code    TEXT    NOT NULL REFERENCES ref.vendors,
    invoice_date   DATE    NOT NULL,
    service_month  TEXT    NOT NULL,
    scope          TEXT    NOT NULL,          -- city (3PL) or warehouse (packaging, loaders)
    po_no          TEXT REFERENCES vnd.purchase_orders,
    item           TEXT    NOT NULL,
    quantity       NUMERIC NOT NULL,
    rate           NUMERIC NOT NULL,
    amount         NUMERIC(18,2) NOT NULL
);
