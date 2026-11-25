"""Build the capstone lake: bronze (raw preserved) + silver (query-ready)
zones from data/raw/*.jsonl.

Contract
--------
    build(raw_dir, out_dir) -> dict

- `raw_dir`: directory containing `part-*.jsonl` (task-01 row schema).
- `out_dir`: lake root, e.g. `data/capstone-lake`. Must be safe to call
  more than once — re-running replaces the previous output, it does not
  append to it.

Zones
-----
**Bronze** (`out_dir/bronze/`): raw preserved, verbatim or lightly
normalized, as Parquet. Your choice how "lightly normalized" — document
the decision in NOTES.md. The point of bronze is that silver can be
cheaply rebuilt from it without going back to JSONL. No partitioning or
sort requirement.

**Silver** (`out_dir/silver/month=YYYY-MM/`): the query-ready zone.

- Hive-partitioned by month (derived from `captured_at`, UTC).
- zstd-compressed (checked at the column-chunk level).
- Sorted within each partition by `(source_id, captured_at)` — this is
  what makes row-group pruning on `source_id` / `captured_at` work later.
- Explicit schema: reuse the task-01 13-column contract (product_id,
  source_id, url, title, category, brand, price, currency, in_stock,
  captured_at, attrs, scrape_run_id, http_status — see task 01's scaffold
  for exact types). Non-200 rows keep `price` / `in_stock` null.
- Controlled file sizes: a partition must not become either one giant
  file or thousands of tiny ones as data volume grows. Use a target file
  size and a rolling writer cutover (track bytes/rows written to the
  current file; once it crosses the target, close it and open the next
  one in the same partition directory) rather than deciding a fixed
  number of files per partition up front.

Streaming / bounded-memory requirement: never materialize the whole
dataset in memory. Silver's sort only ever needs to happen within one
month's worth of data at a time, never across the whole dataset — bucket
by month first (bounded number of simultaneously "hot" months), then sort
and write each month's rows.

Returns
-------
A manifest dict describing what was built. Exact shape is your call — the
validator checks the zones on disk, not the manifest's internal
structure — but it should be honest enough for another engineer to read
before touching the pipeline: at minimum, rows in / rows out and file
count for each zone (bronze, silver).
"""


def build(raw_dir, out_dir):
    raise NotImplementedError(
        "implement build: stream raw_dir into a bronze zone and a month-partitioned, "
        "sorted, size-controlled silver zone under out_dir, returning a manifest dict"
    )
