-- Task 04: price-change-detection
-- Expected output columns (in order): product_id, source_id, captured_at, prev_price, price, drop_pct
-- Write your query below.

with price_history as (
    select 
        ps.product_id as "product_id",
        ps.source_id as "source_id",
        ps.captured_at as "captured_at",
        lag(ps.price, 1, 0) over (
            partition by ps.product_id, ps.source_id
            order by ps.captured_at
            ) as "prev_price",
        ps.price as "price"
    from price_snapshots ps
    order by ps.captured_at
)
select 
    ph.product_id,
    ph.source_id,
    ph.captured_at,
    ph.prev_price,
    ph.price,
    round((ph.prev_price - ph.price) / nullif(ph.prev_price, 0) * 100, 2) as "drop_pct"
from price_history ph
where round((ph.prev_price - ph.price) / nullif(ph.prev_price, 0) * 100, 2) > 70;
