# 02 — Partitions and Shuffles

## Backstory

Source 1 alone accounts for nearly a third of every dump PriceWatch's scrapers produce. The first time you run a naive `groupBy("source_id")` over the full dataset, one task in that stage does roughly six times the work of an average task, sits there long after its siblings have finished, and drags the whole stage's wall time down to whatever that one task takes. This is skew, and it's not a bug — it's what a Zipf-shaped source distribution does to a hash partitioner that has no idea some keys are far more common than others. You've read about salting as the fix. This task makes you build it, watch the partition sizes before and after with your own eyes (via a real per-partition row count, and via the Spark UI), and prove the fix actually flattens the distribution rather than just moving the imbalance somewhere else.

Along the way you'll also nail down two things that are easy to be fuzzy about: what actually controls how many partitions a shuffle produces (`spark.sql.shuffle.partitions`, not the number of input files, not the number of distinct keys), and the difference between `repartition` (always shuffles) and `coalesce` (merges partitions locally, no shuffle, when you're only reducing count).

## What's given

- `data/raw-events/*.jsonl` and `data/ground-truth.json` (same dataset as task 01).
- `src/partitions.py` — three function signatures, fully documented, all raising `NotImplementedError`.
- `tests/bench.py` — **fully implemented, not yours to edit.** Times a naive per-source aggregation against a salted one on the current dataset and writes `results-local.json`. This is informational — read it, watch `localhost:4040` while it runs — but it is not what `validate.py` gates on. Do not copy its salting approach directly into `src/partitions.py`: it demonstrates *a* way to salt for a timed end-to-end query; your function has a different, more specific contract (see below) that the validator actually checks.
- `tests/validate.py` — the validator (runs in-container, needs a live SparkSession).

## What's required

Implement all three functions in `src/partitions.py`. As in task 01, disable AQE (`spark.conf.set("spark.sql.adaptive.enabled", "false")`) inside every function that measures a partition count or inspects a plan — AQE coalesces shuffle partitions after the fact, which makes `df.rdd.getNumPartitions()` report `1` on an un-executed adaptive plan regardless of what actually ran (verified empirically; see NOTES prompts).

1. **`repartition_vs_coalesce(spark, jsonl_dir, target_partitions_repartition, target_partitions_coalesce)`** — read the raw events, report the initial partition count, then produce a `repartition(N)` version and a `coalesce(M)` version. Return partition counts and plans for both.

2. **`shuffle_partitions_effect(spark, jsonl_dir, configured_values)`** — for each value in `configured_values` (at least two), set `spark.sql.shuffle.partitions` to that value, run a `groupBy("source_id")` aggregation, and report the resulting DataFrame's partition count. It should equal the configured value each time (with AQE off).

3. **`skew_partition_counts(spark, jsonl_dir, n_salts, n_partitions)`** — the core of this task. Compute per-partition row counts of the pre-final-aggregation shuffle stage for two variants: naive (partition by `source_id` directly) and salted (partition by a salted key derived from `source_id`, using `n_salts` salt buckets). Then produce the correctly de-salted per-source row counts (deduplicated first) and confirm they still match ground truth.

Full docstrings with exact key names are in `src/partitions.py`.

Then run (from the module root):

```bash
./run.sh 02-partitions-and-shuffles/tests/bench.py       # informational timings + Spark UI, watch localhost:4040
./run.sh 02-partitions-and-shuffles/tests/validate.py    # the actual gate
```

Fill in `NOTES.md`: your chosen `n_salts` and why, what you saw in the Spark UI's stage/task view for the naive run vs the salted run, and what `tests/bench.py`'s timings did or didn't show (local-mode timing gains from salting can be modest or even negative on `local[*]` with a small dataset — the row-distribution numbers are the real signal here, say so if that's what you saw).

## Completion criteria

`tests/validate.py` prints `PASSED`. It checks:

- `repartition_vs_coalesce`: the repartition plan contains `Exchange`; the coalesce plan does not; the reported partition counts match what you asked for.
- `shuffle_partitions_effect`: for at least two distinct configured values, the resulting partition count equals the configured value, and the two results differ from each other.
- `skew_partition_counts`:
  - a **skew ratio** (max partition row count / mean partition row count) computed from your naive partition counts, and the same ratio computed from your salted partition counts;
  - the salted ratio must be smaller than the naive ratio by a structural margin (a ratio-of-ratios threshold, not an absolute number — this holds at 2M rows and should still hold at 50M);
  - the de-salted, deduplicated per-source row counts must match `ground-truth.json`'s `rows_by_source` exactly.
- `results-local.json` exists with timing data for both variants (written by `tests/bench.py`, not hand-edited).
- `NOTES.md` has real content.

## Estimated evenings

1-2

## Topics to read up on

- Hash partitioning and why a fixed number of buckets doesn't imply balanced buckets under a skewed key distribution
- `spark.sql.shuffle.partitions` vs the partition count of a DataFrame read from files
- `repartition()` vs `coalesce()`: when each shuffles and when a shuffle is avoidable
- Key salting for skewed aggregations, and why the salted result needs a second aggregation pass to undo the salt
- Adaptive Query Execution (AQE) and what it changes about partition counts and plan shape at runtime vs at plan-build time
- Reading the Spark UI's Stages tab: task duration distribution within a stage as a skew signal
