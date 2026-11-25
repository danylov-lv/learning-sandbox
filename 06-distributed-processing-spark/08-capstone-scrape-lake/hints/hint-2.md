# Hint 2 — narrowing down the mechanism

**CP1.** `build_silver` is one straight-line pipeline: read, drop
`_corrupt_record`, whole-row `.distinct()`, two `F.broadcast(...)`-hinted
joins (sources on `source_id`, categories on `category_id`), capture the
plan on that joined DataFrame *before* touching `month` at all, then
derive `month`, repartition by it, and write. The order matters for the
plan capture specifically: if you derive `month` or repartition before
capturing the plan, you're capturing a different (and less interesting)
DataFrame's plan than the one the validator checks. `spark.read.json` on
`*.jsonl` and `spark.read.option("header", True).option("inferSchema",
True).csv(...)` are the same reads task 01/03/06 already used.

**CP2.** The naive query is: filter to two fixed months, aggregate each
by `(product_id, source_id)`, inner-join the two aggregates on those same
two columns, join the result to a small `source_id -> region` table, roll
up by region. `run_naive` sets `autoBroadcastJoinThreshold` to `-1` —
read the module docstring in `src/tuned.py` for why this task doesn't
lean on the size-based auto-broadcast heuristic to produce a sort-merge
join naturally (it's real, but it depends on things unrelated to the
query, like whether the read was cached first). With `-1`, the
step-3 join is guaranteed sort-merge, deterministically, regardless of
dataset scale. That's the join to watch in both functions' plans.

For `run_tuned`, the fix is not "turn on AQE and hope." It's specific:
turn AQE on (so the planner *can* revise its choice using real
post-aggregation sizes), reset `autoBroadcastJoinThreshold` back to its
default (do not leave it at run_naive's `-1` — this is the concrete
gotcha the module docstring walks through), explicitly broadcast the
tiny region dimension (don't rely on auto-broadcast even after
resetting the threshold — be deliberate), and size `shuffle.partitions`
down from the 200 default to something that matches how many distinct
`(product_id, source_id)` groups actually exist per month at this
dataset's scale (count them — `groupBy(...).count()` on one month's
slice tells you).
Remember `run_tuned` itself must not call any action — it only builds and
returns the DataFrame. The validator materializes it once and re-captures
the plan afterward, because an AQE plan's `== Final Plan ==` section is
only trustworthy once something has actually run; if you want to see that
same behavior yourself while developing, do it in a scratch script, not
inside `run_tuned`.
