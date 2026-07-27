-- Task 06: top-n-per-group
-- Expected output columns (in order): category_name, rank, product_id, product_name, max_price
-- Write your query below.
with top_n_per_group as (
 select
    c2.name as "category_name",
    row_number() over (
        partition by c2.name
        order by max(ps.price) desc, p.id asc
    ) as "rank",
    p.id as "product_id",
    p.name as "product_name",
    max(ps.price) as "max_price"
from price_snapshots ps
join sources s ON s.id = ps.source_id
join products p on p.id = ps.product_id
join categories c3 ON c3.id = p.category_id
join categories c2 on c2.id = c3.parent_id
join categories c1 on c1.id = c2.parent_id
join categories c0 on c0.id = c1.parent_id
where s.currency = 'USD'
and ps.captured_at >= '2025-06-01' and ps.captured_at < '2025-07-01'
and c0.name = 'Toys & Hobbies'
group by c2.name, p.id, p.name
order by c2.name, p.id, p.name
)
select * from top_n_per_group tpg where tpg.rank <= 3
