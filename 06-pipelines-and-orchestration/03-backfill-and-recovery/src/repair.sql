-- Given: exact deletion for the hole-repair drill. Deletion isn't the
-- exercise here — repairing it is. Run this against the warehouse (e.g.
-- `cat src/repair.sql | docker compose exec -T warehouse psql -U sandbox -d pipelines`)
-- only after you've confirmed all 14 days are correctly backfilled.

DELETE FROM staging.price_records_raw
WHERE dt IN ('2025-06-06', '2025-06-07', '2025-06-08');
