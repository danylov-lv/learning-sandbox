# 03 — Row Groups and Pushdown

## Backstory

The analysts' dashboard has one query shape that runs constantly: "give me everything source X scraped in this date window." Right now that means decompressing and scanning the entire Parquet file every time, because nobody ever built an index. Parquet already carries one, for free, if you write the file so it can be used: every row group stores the min/max of every column, and a reader can skip a whole row group without decompressing a single page if the predicate can't possibly match. Whether that skip actually happens depends on two decisions you make at write time — how big each row group is, and whether the rows are sorted so that a row group's min/max range is actually narrow. This task makes you measure both.

## What's given

- `data/raw/part-*.jsonl` and `data/ground-truth.json`, including `filter_probe` — the exact query the dashboard runs: `source_id == filter_probe.source_id` and `captured_at` within `[filter_probe.captured_at_from, filter_probe.captured_at_to]` inclusive (both whole days, UTC).
- `tests/bench.py` — writes all six variants via your code, then for each one runs the probe query two ways: (a) actual predicate pushdown through `pyarrow.dataset`, timed; (b) a metadata-only pass counting how many row groups' min/max statistics overlap the probe range at all, versus the total row group count. Produces `results-local.json`.
- `tests/validate.py` — the validator.

**Exact probe boundary semantics** (verify this against `generate.py` yourself before trusting it — it is not an assumption, it is inspectable): the probe is a half-open interval `captured_at >= captured_at_from 00:00:00Z` and `captured_at < (captured_at_to + 1 day) 00:00:00Z`. Since `captured_at_to` is a whole day, this is equivalent to "through `captured_at_to` 23:59:59.999999Z inclusive" — the half-open form just avoids any microsecond-boundary argument. `tests/bench.py` implements it exactly this way; read it if you want to see the boundary handled in code.

## What's required

Implement `src/write_rowgroups.py`: `write_all(raw_dir, out_dir) -> dict`.

Stream `data/raw/*.jsonl` and produce six Parquet files under `out_dir`, all zstd level 3, all using the task-01 13-column schema (see the scaffold docstring for exact types):

- `snapshots-rg8k-unsorted.parquet` — `row_group_size=8192`, rows in stream order
- `snapshots-rg128k-unsorted.parquet` — `row_group_size=131072`, rows in stream order
- `snapshots-rg1m-unsorted.parquet` — `row_group_size=1048576`, rows in stream order
- `snapshots-rg8k-sorted.parquet` — `row_group_size=8192`, rows globally sorted by `(source_id, captured_at)`
- `snapshots-rg128k-sorted.parquet` — `row_group_size=131072`, rows globally sorted by `(source_id, captured_at)`
- `snapshots-rg1m-sorted.parquet` — `row_group_size=1048576`, rows globally sorted by `(source_id, captured_at)`

"Globally sorted" means sorted across the entire dataset, not just within whatever chunk you happen to be holding in memory. At the module's default 5 GB scale this will not fit in memory as a single Python list or Arrow table — sorting it anyway is the actual exercise. You have design freedom here: an external merge sort (sort bounded chunks, spill each to a temp file, k-way merge while writing the final files) and a partition-by-source approach (bucket rows by `source_id` into per-source temp files — there are only ~40 sources, so each bucket is small enough to sort in memory — then concatenate buckets in `source_id` order) are both legitimate. Pick one and justify it in `NOTES.md`.

Return `{variant: rows_written}` — all six values equal.

Then run:

```bash
uv run python 03-row-groups-and-pushdown/tests/bench.py
uv run python 03-row-groups-and-pushdown/tests/validate.py
```

In `NOTES.md`, record the pruning ratios `tests/bench.py` prints for each variant and explain, in your own words, why sorting changes what a row group's min/max statistics can tell a reader — and why `rg1m` behaves the way it does on this dataset compared to `rg8k`.

## Completion criteria

`tests/validate.py` prints `PASSED`. It checks:

- all six files exist, each with `num_rows` equal to `ground-truth.json`'s `total_rows`;
- row-group count sanity: `rg8k` has at least 10x more row groups than `rg1m` (same sort order compared to itself) — confirms `row_group_size` actually took effect per variant instead of being ignored or applied once globally;
- probe correctness: every variant's pushdown query returns exactly `filter_probe.rows` rows and `filter_probe.price_sum` (relative tolerance 1e-6) — sorting and row-group size must never change the *answer*, only how much gets skipped to compute it;
- structural pruning targets (measured on the reference dataset, ratio = matching row groups / total row groups):
  - `rg8k-sorted` <= 0.05
  - `rg8k-unsorted` >= 0.5
  - `rg128k-sorted` <= 0.15
  - `rg128k-unsorted` >= 0.5
- `NOTES.md` has real measurements and conclusions, not just the template.

These ratio thresholds were measured against this repository's default test-scale dataset with roughly a 2x safety margin baked in (see `tests/validate.py` for the exact numbers). If you regenerate the dataset at a very different `--gb` size and this task starts failing on the ratio checks specifically (not on correctness), re-measure with `tests/bench.py` and treat that as expected — note what you found in `NOTES.md`.

## Estimated evenings

1-2

## Topics to read up on

- Parquet row-group statistics (per-column min/max, null count) and how a reader uses them for predicate pushdown
- The difference between predicate pushdown (skip whole row groups without reading them) and late filtering (read everything, then filter in memory)
- External sorting: chunk-sort-spill-merge, and why `heapq.merge` is the natural tool for the final k-way merge step
- Partitioned/bucketed sorting as an alternative to a full external sort when the partition key has low cardinality
- Zone maps / min-max indexes in other systems (this is the same idea under a different name — ClickHouse, Snowflake micro-partitions, BigQuery)
