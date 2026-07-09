-- q05: brand storefront filter
-- Business: brand landing pages filter the catalog by attrs containment;
--           marketing buys traffic straight to these URLs.
-- Screaming: SEO/growth team — bounce rate on brand pages doubled.
-- SLA: p95 < 80 ms
SELECT id, title, price, attrs
FROM products
WHERE attrs @> '{"brand": "Peakline"}'
  AND price < 150
ORDER BY created_at DESC
LIMIT 48;
