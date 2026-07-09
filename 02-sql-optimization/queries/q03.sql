-- q03: order detail page
-- Business: renders the line items of one order, with product titles.
--           Runs on every order page view and in every packing-slip print.
-- Screaming: warehouse ops — packing-slip printing queues up.
-- SLA: p95 < 20 ms
SELECT oi.id, oi.quantity, oi.unit_price, p.title
FROM order_items oi
JOIN products p ON p.id = oi.product_id
WHERE oi.order_id = 4242
ORDER BY oi.id;
