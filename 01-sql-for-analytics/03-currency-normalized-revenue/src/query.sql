-- Task 03: currency-normalized-revenue
-- Expected output columns (in order): month, tier, snapshot_count, usd_revenue
-- Write your query below.
select to_char(ps.captured_at, 'YYYY-MM-01') as "month",
    s.tier,
    count(ps.id) as "snapshot_count",
    round(sum(er.rate_to_usd * ps.price), 2) as "usd_revenue"
from price_snapshots ps
join sources s on ps.source_id = s.id
left join lateral (
    select er.rate_to_usd
    from exchange_rates er
    where er.currency = ps.currency
    and er.rate_date <= ps.captured_at::date
    order by er.rate_date desc
    limit 1
) er on true
group by "month", s.tier;
