# Hint 3 — debugging the gates

## Codec gate

`pyarrow.parquet.ParquetFile(path).metadata` gives you a `FileMetaData`
object. Walk `metadata.row_group(i).column(j).compression` for every row
group and every column in every silver file — the compression codec is
recorded per column chunk, not once per file, so a writer that only
zstd-compresses some columns (or falls back to an implicit default for a
column you didn't ask about) will show up here even though "the writer
call" looked right. If you passed a compression argument only to certain
columns of your write call (some libraries let you pass a dict), that's
the first place to check when this gate fails on files that "should" be
zstd.

## File count / file size gates

The same `ParquetFile(path).metadata` object gives you `num_rows` and the
file's own size is just `path.stat().st_size` — nothing exotic needed
here. If this gate fails, it's almost always one of: your rolling cutover
threshold check happens after writing a whole month's data as one shot
(no cutover logic at all, so you get one giant file); or the cutover
checks in-memory row count instead of a size, so file sizes don't
converge on any particular target. The "last file of a partition is
exempt" rule exists because a rolling-cutover writer will, by
construction, end each partition with a partial file smaller than the
target — that's expected and correct, not a bug to fix. Sort your
per-partition file list (lexicographically, by the file name you chose)
and only check the min-size rule against everything except the last one.

## Row-group pruning gate

Every column chunk's statistics (`row_group(i).column(j).statistics`,
`.min` / `.max`) tell you, without touching a single row, whether that row
group *could* contain a value matching a predicate. A row group "overlaps"
a filter when its stats range intersects the filter's range for every
column in the predicate — for the module's `filter_probe`, that means
both the `source_id` column's `[min, max]` contains the probe's
`source_id`, and the `captured_at` column's `[min, max]` intersects the
probe's date range.

If your fraction of overlapping row groups comes in high, two things to
check, in order: first, is the data actually sorted by `(source_id,
captured_at)` within each partition, or did the sort get lost somewhere
between bucketing and writing (a very common bug: sorting a batch, then
concatenating batches from different upstream chunks without re-sorting
across the concatenation)? Second, is your row-group size small enough
relative to partition size that row groups can actually specialize by
`source_id` — a partition with 20,000 rows and one giant row group will
never prune well no matter how it's sorted, because "the row group's
range" is just "the whole partition's range." Sorting narrows what a row
group's min/max *could* be; a row-group size that's too large throws that
narrowing away by lumping many different `source_id` values back into one
group's statistics.

## `filter_probe` boundary semantics

Read `ground-truth.json`'s `filter_probe` literally: `captured_at_to` is
inclusive of the whole day it names, not a strict upper bound at
midnight. If you build your probe/pruning check as `captured_at <
captured_at_to`, you will silently under-count and the fraction will look
better than it should — check `generate.py`'s own construction of this
probe if you want to see the exact boundary arithmetic it uses.

## Latest-price smoke query

For each probe product ID, "latest" means the row with the maximum
`captured_at` among rows where the price observation actually succeeded
(non-null price / http_status 200 in this dataset). Ties in `captured_at`
for the same product are vanishingly unlikely at any size this generator
produces — if you hit one in practice, something upstream duplicated a
row, which is worth investigating on its own rather than adding
tie-breaking logic to paper over it.
