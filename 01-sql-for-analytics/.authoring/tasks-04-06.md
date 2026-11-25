# Authoring notes — tasks 04-06

No solution SQL below — design intent and calibration facts only.

## 04-price-change-detection

Intent: force `LAG()` over a partitioned/ordered window, plus the "filter a
window function result" gotcha (can't reference it in the same `WHERE`).
Trap: consecutive-snapshot comparison, not comparison-to-a-fixed-baseline —
easy to accidentally compare to the day's first or the pair's minimum
instead of the true previous row. Threshold calibrated against the actual
consecutive drop_pct distribution on this seed: >70% yields 38 rows (>60%
would give 254, too many; >80% gives essentially 1). No tie-breaking needed
since (product_id, source_id, captured_at) is already unique per row.
Expected shape: 38 rows.

## 05-rolling-price-volatility

Intent: `ROWS` vs `RANGE` frame semantics, motivated by genuinely irregular
snapshot cadence in the seed (same-pair gaps range from minutes to several
days). Trap: a `ROWS N PRECEDING` window looks plausible and even runs
without error, but on this cadence it silently mixes a few-hours span with a
multi-week span depending on where you sample, giving materially different
avg/max rolling stddev than a calendar-correct `RANGE INTERVAL '30 days'
PRECEDING` window (verified: for the top pair, avg rolling stddev 2.86
RANGE vs 1.95 ROWS(5); max 14.64 RANGE vs 29.66 ROWS(5) — same data, visibly
different numbers). Scope fixed to the 10 highest-snapshot-count pairs in the
seed (500-605 snapshots each, spanning the full 2025-01-01..2026-06-30
range) so the summary stays at exactly 10 rows regardless of per-snapshot
row count.

## 06-top-n-per-group

Intent: `ROW_NUMBER` vs `RANK`/`DENSE_RANK` tie behavior. Trap: real price
ties are common in this seed (checked: dozens of exact-price collisions per
level-2 category in the target month), so a naive `RANK()`-based "top 3"
does produce >3 rows for some categories — this isn't a hypothetical, it
reproduces on the real data. Deterministic fix requires `product_id ASC` as
a secondary sort key inside `ROW_NUMBER() OVER (...)`. Scope: root category
`Toys & Hobbies` (`categories.id = 4`, level 0), all 16 level-2
subcategories in its subtree, USD-currency sources only, June 2025, price =
per-product max observed price that month. All 16 subcategories have >=3
qualifying products, so exactly 48 output rows.
