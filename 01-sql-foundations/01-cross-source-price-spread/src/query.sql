-- Task 01: cross-source-price-spread
-- Expected output columns (in order): root_category, tier, distinct_products, distinct_sources, snapshot_count, min_price, avg_price, max_price
-- Write your query below.

select 
    c.name as "root_category",
    s.tier as "tier",
    count(distinct p.id) as "distinct_products",
    count(distinct s.id) as "distinct_sources",
    count(ps.id) as "snapshot_count",
    min(ps.price) as "min_price",
    round(avg(ps.price), 2) as "avg_price",
    max(ps.price) as "max_price"
from categories c
join categories c1 on c1.parent_id = c.id
join categories c2 on c2.parent_id = c1.id
join categories c3 on c3.parent_id = c2.id
join products p on p.category_id = c3.id
left join price_snapshots ps on ps.product_id = p.id
join sources s on ps.source_id = s.id
where s.currency = 'USD'
and ps.captured_at >= '2025-06-01'
and ps.captured_at < '2025-07-01'
group by "root_category", "tier"
having count(ps.id) > 0
