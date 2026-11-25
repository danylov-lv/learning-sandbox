# Authoring notes — tasks 07-10 (off-limits to the learner before attempting)

## 07 — time-bucketed-trends

Design intent: teach that a "trend chart" query bundles three distinct questions
(volume, distinct-entity coverage, price signal) that must be computed with separate
aggregates, not derived from one another. Trap: `COUNT(*)` where `COUNT(DISTINCT
product_id)` is needed inflates the product count whenever a product has multiple
sources — this is exactly the bug the backstory describes. Secondary trap:
restricting to USD via `WHERE` instead of `FILTER (WHERE ...)` silently drops non-USD
rows from every other aggregate in the same query, not just the price average.
Grouping key is `date_trunc('week', captured_at)` cast to date, joined to `sources`
for `tier`. Result shape: 237 rows (79 ISO week buckets x 3 tiers) — verified via
`SELECT COUNT(DISTINCT date_trunc('week', captured_at)) FROM price_snapshots` = 79.

## 08 — gaps-and-islands

Design intent: canonical gaps-and-islands via the row-number-difference technique.
Trap: naive `LAG()`-based flagging identifies run *boundaries* but not run
*membership* — learners who stop at "flag where the previous row differs" have no
group key to aggregate on. The fix is two `ROW_NUMBER()` windows (one partitioned by
pair only, one partitioned by pair + in_stock) whose difference is constant within a
run. Verified no `captured_at` ties exist for any `(product_id, source_id)` pair in
this seed, so `ORDER BY captured_at` alone is a total order within a partition — no
extra tie-breaker needed inside the window functions themselves. Tie-breaker chain
in the README (`streak_snapshots desc, product_id asc, source_id asc, streak_start
asc`) makes the top-25 cut deterministic; verified rows 25/26 at the cutoff
(`streak_snapshots = 10`) differ by `product_id` (89618 vs 140857), so the cut is
unambiguous. Result shape: exactly 25 rows (`LIMIT 25`).

## 09 — dedup-latest-snapshot

Design intent: `DISTINCT ON` / `ROW_NUMBER()` dedup with an explicit tie-breaker
(`captured_at DESC, id DESC`). Checked the actual data: there are zero
`(product_id, source_id, captured_at)` collisions in this seed (`COUNT(*) FROM
(GROUP BY product_id, source_id, captured_at HAVING COUNT(*) > 1)` = 0). So the "two
calls return different prices" bug from the backstory is not reproducible against
this seed as-is — the README says this explicitly and still mandates the
tie-breaker so the query is correct by construction, not correct by luck of the
data. If a future reseed introduces same-timestamp duplicates (e.g. by lowering
scrape interval variance), this task would then also demonstrate the bug live.
Result shape: 12 rows (3 tiers x 4 currencies, full cross product observed).

## 10 — capstone-pricing-report

Design intent: multi-CTE capstone combining a recursive tree rollup, an as-of
currency join, `percentile_cont` for a real median, and a `LAG()`-based MoM window,
structured as 3 checkpoints matching the CTE stages (base/monthly/final). Checked
`exchange_rates`: this seed has complete daily coverage per currency (546/546 days,
no gaps) — the as-of `LATERAL ... ORDER BY rate_date DESC LIMIT 1` join is required
by the task text as the *correct general technique* (and reused from the trap
description in task 03) even though it degrades to an exact-date match on this
particular seed; a future reseed with sparse `exchange_rates` would exercise it for
real. Verified CP1 self-check: base CTE row count = 4,000,000 (= total
`price_snapshots`, no join loss/fanout). Verified CP2 self-check: exactly 8 distinct
`root_name` values, exactly 144 (month, root) combinations (18 months x 8 roots, full
cross product — no empty buckets). Result shape: 144 rows.
