"""Write six Parquet variants of the price-snapshot data, varying row-group
size and sort order, to measure predicate-pushdown pruning.

Contract
--------
    write_all(raw_dir, out_dir) -> dict

- `raw_dir`: directory containing `part-*.jsonl` (task-01 row schema).
- `out_dir`: directory to write into (create it if missing).

Stream `raw_dir` and produce six Parquet files under `out_dir`, all zstd
level 3, all using this 13-column schema, in this exact order and type:

    product_id      int64
    source_id       int64
    url             string
    title           string
    category        string
    brand           string
    price           float64, nullable
    currency        string
    in_stock        bool, nullable
    captured_at     timestamp[us, tz=UTC]
    attrs           string  (the nested `attrs` dict re-serialized as JSON text)
    scrape_run_id   string
    http_status     int64

Non-200 rows carry `price: null` / `in_stock: null` in the source data —
preserve those as nulls, never coerce to 0 / False.

Output files, all under `out_dir`:

    snapshots-rg8k-unsorted.parquet    row_group_size=8192,    stream order
    snapshots-rg128k-unsorted.parquet  row_group_size=131072,  stream order
    snapshots-rg1m-unsorted.parquet    row_group_size=1048576, stream order
    snapshots-rg8k-sorted.parquet      row_group_size=8192,    sorted
    snapshots-rg128k-sorted.parquet    row_group_size=131072,  sorted
    snapshots-rg1m-sorted.parquet      row_group_size=1048576, sorted

"Sorted" means globally sorted across the entire dataset by
`(source_id, captured_at)` — not sorted within whatever chunk you happen to
be holding in memory. `row_group_size` must actually take effect per file:
each written table must be handed to the writer in exactly the target
row-count chunks (a single `write_table` call with `row_group_size=N` only
caps the row groups produced *from that call*; it does not accumulate
across separate calls).

Streaming / bounded-memory requirement: never materialize the whole dataset
(or even one full sorted copy of it) as a single in-memory Python list or
Arrow table. At the module's default scale this will not fit in memory, so
the sorted variants require an actual external sort — e.g. chunk-sort-spill
temp files then a k-way merge (`heapq.merge`), or bucket rows by
`source_id` into per-source temp files (low cardinality, ~40 sources) and
concatenate buckets in `source_id` order. Either strategy is legitimate;
justify your choice in NOTES.md.

Returns
-------
dict mapping each of the six variant names above (e.g. "rg8k-unsorted",
"rg1m-sorted") to the number of rows written for that variant. All six
values must be equal.
"""


def write_all(raw_dir, out_dir):
    raise NotImplementedError(
        "implement write_all: stream raw_dir, write six row-group/sort-order variants to out_dir"
    )
