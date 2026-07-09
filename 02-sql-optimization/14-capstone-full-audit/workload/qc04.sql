-- qc04: brand + color facet search
-- Business: storefront facet filters ("brand: Nexara" + "color: green") let
--           shoppers narrow the catalog by two attrs at once; facet
--           combinations are driven straight by marketing's landing pages.
-- Screaming: growth team -- combined-facet landing pages convert worse than
--           single-facet ones and the difference tracks page load time.
-- SLA: p95 < 80 ms
SELECT id, title, price, attrs
FROM products
WHERE attrs @> '{"brand": "Nexara", "color": "green"}'
ORDER BY price ASC
LIMIT 40;
