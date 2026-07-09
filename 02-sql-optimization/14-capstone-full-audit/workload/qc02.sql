-- qc02: order total reconciliation
-- Business: nightly billing job recomputes each order's total straight from
--           its line items and flags any order where it disagrees with the
--           stored total_amount (rounding bugs, promo-code edits, etc).
-- Screaming: billing team -- the reconciliation job now blows past its
--           overnight window and delays the morning finance report.
-- SLA: p95 < 30 ms (per order looked up)
SELECT o.id, o.total_amount, sum(oi.quantity * oi.unit_price) AS computed_total
FROM orders o
JOIN order_items oi ON oi.order_id = o.id
WHERE o.id = 4242
GROUP BY o.id, o.total_amount;
