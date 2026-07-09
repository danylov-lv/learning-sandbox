-- q06: catalog text search
-- Business: the header search box does a substring match on product titles
--           (the "real" search service was never finished).
-- Screaming: everyone — search is the #1 complaint in the NPS survey.
-- SLA: p95 < 150 ms
SELECT id, title, price
FROM products
WHERE title ILIKE '%titanium%'
ORDER BY price ASC
LIMIT 50;
