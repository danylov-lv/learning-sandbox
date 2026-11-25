# Authoring notes: tasks 01-03

## 01-cross-source-price-spread

Warm-up: multi-table join + GROUP BY with a shallow tree traversal
(leaf -> level2 -> level1 -> root, 3 hops, no recursion needed since depth is
fixed at 4 levels). Trap being planted: joining `products` to `categories`
at multiple levels naively (all in one big join, aggregating afterward) can
silently fan out `price_snapshots` rows if the category-to-root mapping isn't
resolved as a 1:1 lookup first. Scope pinned to USD-currency sources and
June 2025 to keep row counts stable and currency conversion out of scope
(reserved for task 03). Expected shape: 24 rows (8 root categories x 3
tiers), verified all 24 combinations are populated in this dataset.

## 02-category-tree-rollup

Recursive CTE warm-up over `categories` (adjacency list, parent_id). No
real trap here — the point is mechanical fluency with `WITH RECURSIVE`,
distinguishing anchor vs. recursive member, and computing per-root subtree
stats (count, leaf count, max depth) plus a product-count rollup and a
window-function percentage. Verified structural leaves (no children) exactly
coincide with `level = 3` in this dataset (352 = 352), so the README's
"derive leafness structurally" instruction doesn't fight the data — a
solution using either approach converges to the same answer, but only the
structural one is provably correct in general. Expected shape: 8 rows (one
per root category), tree is 4 levels deep for every root in this seed.

## 03-currency-normalized-revenue

As-of / temporal join. The originally planned trap ("exchange rate table has
calendar gaps") does not hold in this seed — `exchange_rates` has full daily
coverage for all 4 currencies across the whole snapshot date range (verified
via `generate_series` anti-join, zero missing dates). The real trap is a type
mismatch: `price_snapshots.captured_at` is a `TIMESTAMP` with a real
time-of-day component, while `exchange_rates.rate_date` is a bare `DATE`. A
naive `rate_date = captured_at` equi-join implicitly casts `rate_date` to
midnight and only matches snapshots captured at exactly `00:00:00` — verified
this drops the join from 4,000,000 matching rows down to 37. The correct fix
is an as-of join (`rate_date <= captured_at::date`, take the most recent),
implemented in the reference query via `JOIN LATERAL ... ORDER BY rate_date
DESC LIMIT 1`. README frames the trap through the row-count sanity check
without naming the type-mismatch mechanism directly. Expected shape: 54 rows
(18 months x 3 tiers), snapshot_count column sums to exactly 4,000,000
(all price_snapshots rows), confirming no data is lost.
