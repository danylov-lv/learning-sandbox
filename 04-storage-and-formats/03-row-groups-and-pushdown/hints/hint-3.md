One workable plan for the whole task, in words:

**Unsorted variants (rg8k/rg128k/rg1m-unsorted):** this is a single streaming pass with no sort. Open three writers (one per target row_group_size), and for each writer keep its own row buffer. Read raw JSONL rows once; for each row, append it to all three buffers. Whenever a buffer reaches its target size, hand it to its writer as one table (with `row_group_size` set to that exact count so it lands as a single row group) and reset the buffer. Flush whatever's left in each buffer at the very end. This reads the JSONL exactly once for all three unsorted variants.

**Sorted variants (rg8k/rg128k/rg1m-sorted):** this needs an actual external sort first, then the same buffering trick, fed from the sorted stream instead of raw order.
1. Read raw JSONL in bounded chunks (e.g. 100k-300k rows), sort each chunk in memory by `(source_id, captured_at)`, write each sorted chunk to a small temporary Parquet file ("spill file"). Any codec is fine for spill files — they get deleted afterward, speed matters more than ratio there.
2. Open a Parquet reader on each spill file and pull rows out in order (`iter_batches` gives you ordered batches from a single sorted file). Feed all these per-file iterators into `heapq.merge(*iterators, key=...)` keyed on `(source_id, captured_at)` — this produces one globally-ordered stream without ever holding more than one buffered batch per spill file in memory at once.
3. Feed that merged stream into the same three-writer/three-buffer flush logic you used for the unsorted variants, this time targeting the `-sorted.parquet` output files.
4. Delete the spill files.

If you'd rather partition by `source_id` instead (there are only ~40 of them): write one temp file per source, sort each by `captured_at` alone (small, fits in memory), then read them back in `source_id` order and feed that into the same buffering step. This avoids the heap-merge machinery entirely at the cost of ~40 open-file-handles-at-once during the bucketing pass — a fine tradeoff to write about in `NOTES.md`.

For the probe/pushdown side, `tests/bench.py` already does the work — you don't write any query code for this task, only the six files.
