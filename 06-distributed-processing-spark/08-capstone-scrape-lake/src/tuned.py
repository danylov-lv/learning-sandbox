"""CP2 — shuffle-tuning pass over the silver lake, measured.

The question: for a fixed pair of adjacent months, how did each region's
average per-(product, source) price move month over month? Concretely:

  1. Restrict silver to http_status == 200 rows in MONTH_A and MONTH_B.
  2. Aggregate each month separately: avg(price) grouped by
     (product_id, source_id).
  3. Inner-join the two monthly aggregates on (product_id, source_id) —
     this is the expensive step: at the committed 2M-row dataset each
     side already has tens of thousands of groups, and at 50M+ rows far
     more. It is also the join whose broadcast-vs-shuffle decision this
     checkpoint is about.
  4. Join the per-(product, source) deltas to a small source_id -> region
     dimension (20 rows) and roll up: sum(delta), avg(delta), count(*),
     grouped by region.

Both functions below build and return this same logical query — same
input, same joins, same final grouping — over the silver lake written by
`pipeline.build_silver` (CP1). What must differ is *how* Spark executes
it, not what it computes. Do not call `.collect()`, `.count()`, or any
other action inside either function — return the unmaterialized final
DataFrame and let the caller (tests/bench.py for timing, tests/validate.py
for correctness/plan checks) decide when to run it.

Both functions must set every relevant session config explicitly at the
top, not rely on whatever the other one (or an earlier call in the same
session) left behind — config set via spark.conf.set persists across
calls on a shared SparkSession (see task 03's contract for the same
warning, and this task's own README/NOTES for a concrete instance of this
biting: forgetting to reset autoBroadcastJoinThreshold in run_tuned after
run_naive lowered it leaves the broadcast hint fighting a threshold that
overrides it).

MONTH_A = "2025-11", MONTH_B = "2025-12" — fixed so the job is
reproducible at any dataset scale (every generated dataset spans
2025-01..2026-06).

A note on *why* the step-3 join needs an explicit push in either
direction: whether Spark's planner auto-broadcasts a `groupBy(...).agg(...)`
result with no hint and no forced threshold turns out to depend on things
that have nothing to do with the query itself — whether the upstream read
was cached, whether the source is JSONL (unreliable size stats) or
Parquet (accurate footer stats). That is not a solid foundation for a
reproducible "naive is slow, tuned is fast" demonstration, so this task
does not lean on it: `run_naive` disables auto-broadcast outright,
`run_tuned` re-enables it and adds AQE plus an explicit hint on the small
side. The point isn't "broadcasting never happens by accident" (it does,
and you may see it in your own experiments if you leave the threshold at
its default and read from Parquet) — the point is a *deterministic*
before/after you can gate a validator on regardless of dataset scale or
what's sitting in cache.
"""

MONTH_A = "2025-11"
MONTH_B = "2025-12"


def run_naive(spark, silver_dest: str):
    """The job with auto-broadcast deliberately taken off the table.

    Required, set at the top of this function:
      - spark.conf.set("spark.sql.adaptive.enabled", "false")
      - spark.conf.set("spark.sql.shuffle.partitions", "200")  # Spark's
        default; set it explicitly so a prior call on this session can't
        leak in either direction
      - spark.conf.set("spark.sql.autoBroadcastJoinThreshold", "-1")
        # disables auto-broadcast for every join in this function,
        # regardless of side size — this is what forces the step-3 join
        # (the two monthly aggregates) onto a sort-merge join
        # deterministically, the same technique task 03's
        # force_sort_merge uses and for the same reason: a size-based
        # heuristic is not a reliable way to guarantee a specific plan
        # shape across dataset scale or caching state (see this module's
        # docstring for the concrete story).
      - No broadcast() hint anywhere in this function.

    Build the query described in this module's docstring exactly as
    written — read silver_dest, filter, aggregate MONTH_A and MONTH_B
    separately by (product_id, source_id), inner-join the two aggregates,
    join to the source_id -> region dimension (read reference/sources.csv
    fresh, no hint), and roll up by region.

    Returns:
        An unmaterialized DataFrame with exactly these columns:
        region (string), sum_delta (double), avg_delta (double),
        n (long) — one row per region present in the join result.
    """
    raise NotImplementedError("implement run_naive")


def run_tuned(spark, silver_dest: str):
    """The same job, deliberately tuned.

    Required, all set explicitly at the top of this function (do not
    assume run_naive's config is still in effect, and do not assume it
    isn't):
      - spark.conf.set("spark.sql.adaptive.enabled", "true")
      - spark.conf.set("spark.sql.shuffle.partitions", ...) sized to the
        data, not left at the 200 default — pick a value and justify it
        in NOTES.md (how many distinct (product_id, source_id) pairs are
        actually in play for one month at the dataset scale you tested,
        and what a reasonable partition count looks like relative to
        that).
      - spark.conf.set("spark.sql.autoBroadcastJoinThreshold", "10485760")
        # Spark's default. Resetting this explicitly matters: if
        # run_naive already ran on this SparkSession and left the
        # threshold at -1, an explicit broadcast() hint on this
        # function's small dimension table will still take effect (a
        # hint overrides the threshold — see task 03), but AQE's runtime
        # conversion of the step-3 join from sort-merge to broadcast will
        # not happen with the threshold still at -1, because AQE's
        # conversion decision is itself governed by this same threshold.
      - The source_id -> region dimension must be broadcast explicitly
        (F.broadcast(...)) rather than left to auto-broadcast — be
        deliberate about the join strategy you're choosing.

    Build the exact same logical query as run_naive (same filter, same
    two monthly aggregates, same join keys, same final grouping) — the
    result must be identical, only the execution plan may differ.

    Returns:
        An unmaterialized DataFrame with exactly these columns:
        region (string), sum_delta (double), avg_delta (double),
        n (long) — one row per region present in the join result, same
        values as run_naive's result (within floating-point tolerance).
    """
    raise NotImplementedError("implement run_tuned")
