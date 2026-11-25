-- Task 07: time-bucketed-trends
-- Expected output columns (in order): week_start, tier, snapshot_count, distinct_products, distinct_product_source_pairs, avg_price_usd
-- Write your query below.
select
    date_trunc('week', ps.captured_at)::date as "week_start",
    s.tier as "tier",
    count(ps.id) as "snapshot_count",
    count(distinct ps.product_id) as "distinct_products",
    count(distinct (ps.product_id, ps.source_id)) as "distinct_product_source_pairs",
    round(avg(ps.price) filter (where ps.currency = 'USD'), 2) as "avg_price_usd"
from price_snapshots ps
join sources s on s.id = ps.source_id
where ps.captured_at::date >= '2025-01-01' and ps.captured_at::date <= '2026-06-30'
group by "week_start", "tier";
