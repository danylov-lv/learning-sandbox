-- Task 05: rolling-price-volatility
-- Expected output columns (in order): product_id, source_id, snapshot_count, avg_rolling_stddev, max_rolling_stddev
-- Write your query below.

with rolling as (
    select
        ps.product_id,
        ps.source_id,
        ps.captured_at,
        STDDEV_SAMP(ps.price) OVER (
            partition by ps.product_id, ps.source_id
            order by ps.captured_at
            range between interval '30 days' preceding and current row
        ) as rolling_stddev_30d
    from price_snapshots ps
    where (ps.product_id, ps.source_id) in (
        (140857, 186),
        (157376, 186),
        (157376, 91),
        (157376, 113),
        (140857, 91),
        (72050, 113),
        (140857, 113),
        (17943, 113),
        (22654, 186),
        (17943, 91)
    )
)
select 
    r.product_id,
    r.source_id,
    count(*) as "snapshot_count",
    round(avg(r.rolling_stddev_30d), 4) as "avg_rolling_stddev",
    round(max(r.rolling_stddev_30d), 4) as "max_rolling_stddev"
from rolling r
group by r.product_id, r.source_id
