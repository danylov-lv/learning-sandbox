-- Given: a stand-in for "some downstream consumer already built on core."
-- Deliberately does not reference seller_rating — it predates that column
-- and has no reason to care about it. Its job here is to prove that
-- evolving the contract (task 06) doesn't break something that was already
-- reading from core.price_records before the drift days existed.
--
-- Must return at least one row for every day that has been loaded into
-- core.price_records, both before and after the contract evolves.

SELECT
    dt,
    category,
    count(*)      AS n_records,
    avg(price)    AS avg_price,
    min(price)    AS min_price,
    max(price)    AS max_price
FROM core.price_records
GROUP BY dt, category
ORDER BY dt, category;
