-- qc06: refund reconciliation
-- Business: finance's weekly refund audit -- how many payments were
--           refunded against orders placed in the last week, and how much
--           money that represents. Joins the orders and payments sides of
--           the ledger, which is the whole point of the report.
-- Screaming: finance -- this used to be a spreadsheet macro; now that it's
--           a live query it's the report they dread running before a close.
-- SLA: p95 < 250 ms
SELECT count(*) AS refund_count, sum(p.amount) AS refund_total
FROM orders o
JOIN payments p ON p.order_id = o.id
WHERE p.status = 'refunded'
  AND o.created_at >= now() - interval '7 days';
