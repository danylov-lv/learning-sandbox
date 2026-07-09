"""Build the deliberately-wrong lake: partitioned by a high-cardinality
column, written the naive way, to demonstrate the small-files trap.

Contract
--------
    build(raw_dir, trap_dir) -> int

- `raw_dir`: directory containing `part-*.jsonl` (task-01 row schema).
- `trap_dir`: directory to write into, e.g. `data/lake-trap`. Safe to call
  more than once — replace previous output, do not append to it.

Produce the same rows as `build_lake.build`, but partitioned by
`category` instead of `month`:

    trap_dir/category=<path>/part-*.parquet

`category` is the row's full 3-level path (e.g. `"electronics/mid/leaf"`),
stored as a single string column — do not split it into separate levels.
Measured cardinality on the reference 400k-row dataset: ~300 distinct
values (verify against your own `data/raw` — if it looks too low, say so
in NOTES.md and pick a different high-cardinality column).

Same 13-column schema and zstd level-3 compression as `build_lake.build`
(see that module's docstring for the exact column list/types). Non-200
rows keep `price` / `in_stock` null.

Requirements
------------
- No sorting requirement.
- No file-count control — write it the naive way: stream raw_dir in
  bounded-size chunks, and for each chunk write straight into the
  partitioned dataset (e.g. via a partitioned dataset writer applied to
  that chunk). Every chunk that touches a category directory drops
  another file into it — that naive-but-reasonable-looking behavior is
  the point of this scaffold.
- Streaming, bounded memory: never materialize the whole dataset in
  memory at once.

Returns
-------
Total number of rows written across all partitions.
"""


def build(raw_dir, trap_dir):
    raise NotImplementedError(
        "implement build: stream raw_dir, write a naive category-partitioned lake to trap_dir"
    )
