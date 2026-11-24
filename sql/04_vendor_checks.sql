-- =====================================================================
-- 04  Vendor billing checks A01-A05 and the escalation log
-- Rules: docs/design.md section 4. Amount at stake = what should not have been charged.
-- =====================================================================

CREATE OR REPLACE VIEW rpt.vendor_checks AS
WITH inv AS (SELECT * FROM vnd.invoices),
grn AS (SELECT po_no, SUM(quantity_received) AS received FROM vnd.grns GROUP BY po_no),
card AS (SELECT * FROM ref.rate_cards),
log3pl AS (                                  -- what the trip log says the 3PL did, per city and month
    SELECT month, city_code, COUNT(*) AS trips, SUM(km_total) AS km
    FROM rpt.trip_facts WHERE owner = '3PL' GROUP BY month, city_code
),
a01 AS (   -- three-way match: invoiced quantity above quantity received
    SELECT 'A01' AS check_code, i.vendor_code, i.invoice_no, i.service_month, i.scope,
           format('Invoiced %s %s, received %s (PO %s)', i.quantity, i.item, g.received, i.po_no) AS detail,
           (i.quantity - g.received) * i.rate AS amount_at_stake
    FROM inv i JOIN grn g USING (po_no) WHERE i.quantity > g.received
),
a02 AS (   -- rate card: billed rate above the contracted rate (services without a PO)
    SELECT 'A02', i.vendor_code, i.invoice_no, i.service_month, i.scope,
           format('%s billed at %s, contract rate %s', i.item, i.rate, c.rate),
           (i.rate - c.rate) * i.quantity
    FROM inv i JOIN card c ON c.vendor_code = i.vendor_code AND c.rate_code = i.item
     AND to_date(i.service_month || '-01', 'YYYY-MM-DD') BETWEEN c.valid_from AND c.valid_to
    WHERE i.po_no IS NULL AND i.rate > c.rate
),
a03 AS (   -- trip log: 3PL trips or km billed above what the trip log shows
    SELECT 'A03', i.vendor_code, i.invoice_no, i.service_month, i.scope,
           format('%s billed %s, trip log %s', i.item, i.quantity, CASE i.item WHEN 'KM' THEN l.km ELSE l.trips END),
           (i.quantity - CASE i.item WHEN 'KM' THEN l.km ELSE l.trips END) * c.rate
    FROM inv i
    JOIN log3pl l ON l.month = i.service_month AND l.city_code = i.scope
    JOIN card c ON c.vendor_code = i.vendor_code AND c.rate_code = i.item
     AND to_date(i.service_month || '-01', 'YYYY-MM-DD') BETWEEN c.valid_from AND c.valid_to
    WHERE i.vendor_code = 'V01' AND i.quantity > CASE i.item WHEN 'KM' THEN l.km ELSE l.trips END
),
totals AS (SELECT invoice_no, vendor_code, service_month, scope, MIN(invoice_date) AS invoice_date,
                  SUM(amount) AS amount, string_agg(item || ':' || quantity, ',' ORDER BY item) AS lines
           FROM inv GROUP BY 1, 2, 3, 4),
a04 AS (   -- duplicate: same vendor, period, scope, lines and amount under another invoice number
    SELECT 'A04', d.vendor_code, d.invoice_no, d.service_month, d.scope,
           format('Same lines and amount as %s', o.invoice_no), d.amount
    FROM totals d JOIN totals o ON o.vendor_code = d.vendor_code AND o.service_month = d.service_month
     AND o.scope = d.scope AND o.lines = d.lines AND o.amount = d.amount
     AND (o.invoice_date, o.invoice_no) < (d.invoice_date, d.invoice_no)
),
a05 AS (   -- price above PO
    SELECT 'A05', i.vendor_code, i.invoice_no, i.service_month, i.scope,
           format('%s billed at %s, PO %s rate %s', i.item, i.rate, i.po_no, p.rate),
           (i.rate - p.rate) * i.quantity
    FROM inv i JOIN vnd.purchase_orders p USING (po_no) WHERE i.rate > p.rate
)
SELECT check_code, vendor_code, invoice_no, service_month, scope, detail, round(amount_at_stake, 2) AS amount_at_stake
FROM (SELECT * FROM a01 UNION ALL SELECT * FROM a02 UNION ALL SELECT * FROM a03
      UNION ALL SELECT * FROM a04 UNION ALL SELECT * FROM a05) x(check_code, vendor_code, invoice_no, service_month,
                                                                  scope, detail, amount_at_stake);

-- Escalation log: every failed check, with owner, action and due date
CREATE OR REPLACE VIEW rpt.escalation_log AS
SELECT row_number() OVER (ORDER BY i.invoice_date, c.check_code, c.invoice_no) AS escalation_id,
       c.check_code, c.vendor_code, v.vendor_name, c.invoice_no, i.invoice_date, c.service_month, c.scope,
       c.detail, c.amount_at_stake,
       CASE WHEN c.check_code IN ('A01', 'A05') THEN 'Procurement' ELSE 'Finance (accounts payable)' END AS owner,
       CASE c.check_code WHEN 'A04' THEN 'Reject duplicate, do not pay'
                         ELSE 'Hold the disputed amount, request a credit note' END AS action,
       i.invoice_date + 2 AS raised_on,
       i.invoice_date + 7 AS due_on,
       'Open' AS status
FROM rpt.vendor_checks c
JOIN (SELECT invoice_no, MIN(invoice_date) AS invoice_date FROM vnd.invoices GROUP BY invoice_no) i USING (invoice_no)
JOIN ref.vendors v USING (vendor_code);
