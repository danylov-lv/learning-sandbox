# 08 — Capstone: Lake Layout

## Backstory

PriceWatch just signed two more marketplaces, and the finance team wants
five years of retention instead of eighteen months. Call it 10x current
volume, sustained. Over tasks 01-07 you measured every axis in isolation:
Parquet vs CSV vs JSONL, five codecs, three row-group sizes, hive
partitioning vs a high-cardinality trap, MinIO listing cost, Delta Lake
commits and time travel, DuckDB pushdown. Nobody has committed to a single
answer yet.

That's the job now. Pick one layout, build it end to end, and leave behind
something the next engineer can inherit as a lake, not a folder of
experiments they have to re-derive. This capstone has three checkpoints:
a pipeline that actually produces the layout, quality gates that keep it
honest as data grows, and a design memo that defends the choices with the
numbers you already measured.

## What's given

- Everything under `data/` from the module generator and from tasks 01-07
  (you may reuse code, but the capstone does not depend on any task's
  output directory — it reads straight from `data/raw/`).
- `src/build_capstone.py` — a scaffold with the `build(raw_dir, out_dir)`
  contract and a `NotImplementedError`.
- `tests/validate.py` — fully implemented; do not edit it.
- `DESIGN.md` — a template for the CP3 writeup.
- `NOTES.md` — a template for your running measurements.

## What's required

A single re-runnable pipeline, `build(raw_dir, out_dir) -> dict`, that
turns `data/raw/*.jsonl` into a lake under `data/capstone-lake/` with two
zones:

- **Bronze**: raw preserved, verbatim or lightly normalized, as Parquet.
  Your choice how "lightly normalized" — document it in `NOTES.md`. The
  point of bronze is that it is cheap to rebuild silver from without going
  back to JSONL.
- **Silver**: hive-partitioned by month (`month=YYYY-MM/`), zstd-compressed,
  sorted within each partition by `(source_id, captured_at)`, an explicit
  schema (reuse the 13-column contract from task 01), and controlled file
  sizes — a partition should not become either "one giant file" or "ten
  thousand tiny files" as the source data grows.

`build()` must be safe to run more than once (re-running replaces the
previous output, it does not append to it) and must return a manifest
dict: rows in and rows out for each zone, and file counts. The exact
manifest shape is your call — the validator checks the zones on disk, not
the manifest's internal structure — but the manifest is what the next
engineer reads before touching the pipeline, so make it honest.

## Checkpoint 1 — Pipeline (about 1 evening)

Implement `build()`. Run it, then check correctness:

```
uv run python 08-capstone-lake-layout/tests/validate.py --cp1
```

This checks: bronze row count equals `ground-truth.json`'s `total_rows`;
silver row count equals `total_rows`; per-month price sums in silver match
`price_sum_by_month` (relative tolerance `1e-6`); and the set of
`month=YYYY-MM` partitions in silver exactly matches the keys of
`rows_by_month` — no missing months, no extra ones, no off-by-one month
boundaries.

## Checkpoint 2 — Quality gates (about 1 evening)

Structural gates that keep the layout honest as the lake grows, not just
correct once:

```
uv run python 08-capstone-lake-layout/tests/validate.py --cp2
```

- **Codec**: every silver Parquet file is zstd-compressed (checked at the
  column-chunk level, not just "the writer was told zstd").
- **File count**: no silver partition has more than 8 files.
- **File size**: no silver file is smaller than `min(8 MB, partition_bytes
  / 2)`, except the last file in a partition (a partial final file is
  expected and fine — that's how a target-size rolling writer ends).
- **Row-group pruning**: build the row-group statistics so that a filter
  on `source_id` and `captured_at` (using the module's `filter_probe`)
  only forces DuckDB to open row groups that could actually contain a
  match. The gate: at most 15% of all silver row groups overlap the
  probe's range. This is a direct test of whether your sort key is doing
  its job — an unsorted silver zone will not clear this bar once row
  groups get small enough to matter.
- **Smoke query**: a DuckDB query over silver reproduces
  `latest_price_probe` (the latest-price-per-product check from the
  ground truth) for all 10 probe product IDs.

These thresholds are written as ratios (files per partition, bytes
relative to partition size, fraction of row groups), not absolute numbers,
so they mean the same thing at the 400k-row test dataset and at a 5 GB or
50 GB build.

## Checkpoint 3 — Design memo (about 0.5-1 evening)

Fill in `DESIGN.md`. Every claim needs a number behind it — "zstd is a
good default" is not a design decision, "zstd at level 3 cost us 4% size
over level 19 but wrote 6x faster in task 02" is. Sections:

- **Layout and why** — zones, partition key, sort key, codec, each tied to
  a measurement from tasks 01-07.
- **What 10x changes** — file counts, listing cost, compaction cadence.
- **Retention and lifecycle** — what moves to a colder codec/tier, and
  when.
- **What I would do differently with Iceberg/Delta everywhere** — where
  hive-partitioned Parquet already hit its ceiling in tasks 04-06, and what
  a table format would have bought you there.

```
uv run python 08-capstone-lake-layout/tests/validate.py --cp3
```

## Completion criteria

```
uv run python 08-capstone-lake-layout/tests/validate.py
```

with no flags runs all three checkpoints in order and must print `PASSED`
for each. (Running a single `--cp2` or `--cp3` assumes CP1 already built
the lake on disk; it will tell you plainly if it can't find it.)

## Estimated evenings

2-3 (roughly 1 per checkpoint, CP3 can run short)

## Topics to read up on

- Medallion architecture (bronze / silver / gold) and what each zone is
  actually for
- Compaction strategies: rolling file cutover vs. post-hoc rewrite
- Table-format metadata scaling (Parquet footer/row-group stats vs. Delta
  transaction log vs. Iceberg manifests) as file counts grow
- Data lifecycle and storage tiers (hot / warm / cold / archive) and what
  triggers a move between them
- Cost models for object storage: per-GB-month vs. per-request pricing and
  why small-file layouts are expensive on both axes
