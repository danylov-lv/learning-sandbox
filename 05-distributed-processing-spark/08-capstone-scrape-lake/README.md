# 08 — Capstone: Scrape Lake

## Backstory

This is the module finale. PriceWatch's loader has been a single Python
process since day one: read JSONL off disk, dedup in a dict, join
in-memory against two small CSVs, write Parquet by hand. It worked when
"a dump" meant a few hundred thousand rows. It does not work anymore, and
nobody wants to find that out during a scrape-run that produces 50
million events instead of 2.

You're replacing it with the real thing: a Spark job that reads the raw
scraped dumps, drops the malformed lines, dedupes the retry-storm
repeats, enriches every row with source and category reference data, and
lands the result as a partitioned Parquet lake on MinIO — the same
storage substrate module 04 built the layout theory against, except this
time a distributed engine is doing the writing. Then, because landing the
lake correctly is only half the job, you take one deliberately
shuffle-heavy analytical query over that lake, run it two ways, and prove
in the Spark UI — not by eyeballing wall-clock — what specifically your
tuning pass changed.

Three checkpoints, roughly one evening each: the pipeline, the tuning
pass, and a design writeup that makes you defend both with numbers.

## What's given

- `data/raw-events/*.jsonl`, `data/reference/sources.csv`,
  `data/reference/categories.csv`, `data/ground-truth.json` — the same
  dataset every task in this module uses.
- MinIO, already running as part of this module's `docker compose up`,
  bucket `price-lake-05` already created. This capstone namespaces every
  write under `s3a://price-lake-05/capstone/` — task 06 owns
  `task-06/` in the same bucket; do not write outside `capstone/`.
- `src/pipeline.py` — CP1's `build_silver(...)` contract, fully
  documented, raising `NotImplementedError`.
- `src/tuned.py` — CP2's `run_naive(...)` / `run_tuned(...)` contracts,
  fully documented, raising `NotImplementedError`.
- `tests/bench.py` — **fully implemented, not yours to edit.** Times
  `run_naive` and `run_tuned` via a noop write sink and writes
  `results-local.json`.
- `tests/validate.py` — the validator, covering all three checkpoints.
- `DESIGN.md`, `NOTES.md` — templates for the CP3 writeup and your
  running measurements.

## What's required

### Checkpoint 1 — pipeline to silver lake

Implement `build_silver(spark, jsonl_dir, reference_dir, dest)` in
`src/pipeline.py`: drop malformed lines, whole-row dedup, broadcast-join
both reference tables (`sources.csv` on `source_id`, `categories.csv` on
`category_id`), derive a `month` partition column, write Parquet to
`s3a://price-lake-05/capstone/silver` with a controlled, bounded file
count per partition, and return a small report (the joined plan, total
row count, per-month counts).

```bash
./run.sh 08-capstone-scrape-lake/tests/validate.py --cp1
```

This call **is** your write job — it invokes `build_silver` directly, so
running it builds the lake. Re-run it any time you change
`src/pipeline.py`; it overwrites the previous lake.

### Checkpoint 2 — shuffle-tuning pass, measured

Implement `run_naive(spark, silver_dest)` and `run_tuned(spark,
silver_dest)` in `src/tuned.py`: the same month-over-month, per-region
price-delta rollup, computed two ways. `run_naive` disables auto-broadcast
outright (200 shuffle partitions, AQE off, `autoBroadcastJoinThreshold`
forced to `-1`) so its main join sort-merges deterministically, regardless
of dataset scale or what happened to be cached beforehand. `run_tuned` is
the same query with AQE on, the broadcast threshold reset, a deliberately
broadcast reference join, and a shuffle-partition count sized to the
data rather than left at the default. Full contract — including why this
task forces the naive/tuned gap explicitly instead of relying on Spark's
own size heuristic to produce it "naturally" — is in `src/tuned.py`'s
module docstring; read it before you write either function, it explains
a real gotcha (forgetting to reset the broadcast threshold in
`run_tuned` after `run_naive` lowered it) that will otherwise cost you an
hour of confused debugging.

```bash
./run.sh 08-capstone-scrape-lake/tests/bench.py       # timing, writes results-local.json — watch localhost:4040
./run.sh 08-capstone-scrape-lake/tests/validate.py --cp2
```

### Checkpoint 3 — the writeup

Fill in `DESIGN.md`: the silver lake layout defended with your own CP1
numbers, the tuning pass explained with before/after Spark UI
observations from CP2, and the polars-calibration verdict from task 07
folded in — when would this whole pipeline not need Spark at all.

```bash
./run.sh 08-capstone-scrape-lake/tests/validate.py --cp3
```

## Checkpoints

| CP | Evening | Requires | Validate |
|---|---|---|---|
| CP1 | 1 | `build_silver` implemented in `src/pipeline.py` | `./run.sh 08-capstone-scrape-lake/tests/validate.py --cp1` |
| CP2 | 1 | `run_naive`/`run_tuned` implemented in `src/tuned.py`, then `tests/bench.py` run | `./run.sh 08-capstone-scrape-lake/tests/validate.py --cp2` |
| CP3 | 0.5-1 | `DESIGN.md` and `NOTES.md` filled in | `./run.sh 08-capstone-scrape-lake/tests/validate.py --cp3` |

Running `./run.sh 08-capstone-scrape-lake/tests/validate.py` with no
flags runs all three in order and stops at the first failure — the same
convention module 04's capstone uses. CP2 and CP3 tell you plainly if
the checkpoint before them hasn't produced what they need yet (an empty
silver lake, a missing `results-local.json`).

## Watching the Spark UI during CP2

`localhost:4040` only serves pages while a `SparkSession` is alive (see
the module README's "Spark UI" section — no history server here). Run
`tests/bench.py` in one terminal; while it's running (it prints "timing
run_naive ..." then, a bit later, "timing run_tuned ..."), open
`localhost:4040` in a browser. The Jobs tab shows one job per timed run;
open its Stages tab and look at the widest stage's task-duration spread
(max vs. median) and the shuffle read/write bytes columns — that's the
concrete evidence behind "the tuned plan moved less data," not just a
smaller wall-clock number. Record what you saw in `NOTES.md`'s CP2
measurements table before the session ends and the UI goes dark.

## Completion criteria

`./run.sh 08-capstone-scrape-lake/tests/validate.py` prints `PASSED` for
all three checkpoints. Specifically:

- **CP1**: `build_silver`'s returned plan shows at least two
  `BroadcastHashJoin` occurrences and no `SortMergeJoin`; the lake at
  `s3a://price-lake-05/capstone/silver` has exactly `ground-truth.json`'s
  `rows_by_month` counts for all 18 months and `distinct_rows` total;
  `region`/`vertical`/`tier` columns are present; per-region row counts
  match an expectation derived independently (in the validator, no Spark
  involved) from `rows_by_source` combined with `sources.csv`; every
  month partition has between 1 and 8 files.
- **CP2**: `run_naive` and `run_tuned` produce identical per-region
  results (within floating-point tolerance); `run_naive`'s plan contains
  a `SortMergeJoin`; `run_tuned`'s adopted (`== Final Plan ==`) plan
  contains a `BroadcastHashJoin` and no `SortMergeJoin`; `results-local.json`
  (written by `tests/bench.py`) shows `tuned_seconds` clearly below
  `naive_seconds`. The timing margin is generous and was set from
  repeated local measurements (see `tests/validate.py`); the structural
  plan check is the primary gate — read the honesty note in `NOTES.md`'s
  prompts if your own timing looks noisier than that.
- **CP3**: `DESIGN.md` and `NOTES.md` both have real content, well past
  their templates.

## Estimated evenings

2-3 (roughly one per checkpoint; CP3 can run short)

## Topics to read up on

- Broadcast hash join vs. sort-merge join, and the gap between a static
  planner's size estimate and what Adaptive Query Execution measures at
  runtime (this capstone's CP2 sits exactly in that gap)
- s3a committer costs at write time: why a naive `partitionBy` write
  without a prior `repartition` sprays small files, and what that costs
  on an object store specifically (no cheap atomic rename, "directories"
  are a listing convention)
- Choosing a partition column for a lake that's mostly consumed by
  month-scoped queries — what a different grain would cost you
- Sizing `spark.sql.shuffle.partitions` deliberately instead of leaving
  it at the 200 default, and what "too many" vs. "too few" partitions
  each cost
- AQE in tuning practice: shuffle-partition coalescing and when it does
  (and doesn't) rescue a job you didn't otherwise tune
- Reading the Spark UI's Stages tab for shuffle read/write bytes and
  task-duration spread as evidence, not just a wall-clock number
- When a pipeline like this one doesn't need Spark at all (task 07's
  calibration question, revisited at this capstone's scale)
