# Hint 3

For `build_lake.py`:

Check first: is `captured_at` roughly ordered as you read through
`part-*.jsonl`? (Print a sample of months as you go.) If it is not — and it
is worth actually checking rather than assuming — then any strategy that
assumes "recent months stay hot, old ones can be evicted" (an LRU of open
writers) is solving a problem you don't have and will constantly evict and
reopen writers for months that show up again three rows later. There are
only 18 distinct month keys in the whole dataset. That is a small, fixed,
known-in-advance number — just keep one accumulator (an in-memory buffer of
rows, or an open writer) per month for the entire pass, all 18 open at once.
No eviction needed.

Concrete shape of one streaming pass:

1. Open all `part-*.jsonl` files in order, reading line by line / in small
   batches — never materializing the whole raw set.
2. For each row (or small batch of rows), parse `captured_at`, derive the
   month key, and append the row into that month's in-memory buffer.
3. When a given month's buffer crosses a fixed row-count threshold (pick
   something that keeps memory bounded regardless of total dataset size —
   a few hundred thousand rows is plenty), sort that buffer by
   `(source_id, captured_at)`, write it out as one new Parquet file under
   `lake_dir/month=<key>/`, and clear the buffer. Give each flush a unique
   file name so a second flush for the same month doesn't collide with the
   first.
4. After the whole raw set has been consumed, flush whatever is left in
   every still-open buffer (sort, write, one final file per month with
   remaining rows).
5. Sum up and return total rows written.

At the dataset sizes this task actually uses, most months will never even
hit the flush threshold mid-stream — you'll get exactly one file per
partition, written at the final flush. That's fine and expected; the
mechanism still has to be there for it to hold at larger scale.

For `build_trap.py`: skip steps 2-4 above entirely. Read the raw data in
chunks (any bounded chunk size), build an Arrow table per chunk, and call
`write_dataset` directly on that chunk with `partitioning=["category"]`,
`existing_data_behavior="overwrite_or_ignore"`, and a file name that is
unique per chunk (e.g. include a running chunk index or a random id in
`basename_template`). Do this once per chunk, nothing more. Every chunk that
touches a given category directory drops another file into it. That's the
whole "naive" implementation — the point of this scaffold is that it should
look reasonable and still be wrong at scale.
