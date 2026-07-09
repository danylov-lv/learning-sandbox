# Hint 1

Hive partitioning is not a Parquet feature — it is a directory naming
convention (`col=value/`) that a query engine reads before opening a single
byte of data. The partition value never even lives in the file's bytes for
that reason; it comes from the path. This is exactly why a partition column
must be one you actually filter on: pruning happens at directory-listing
time, not scan time. A column nobody filters on gains you nothing by being a
partition and just costs you file-count overhead.

The flip side is cardinality. A partition key is a physical decision, not a
logical one — every distinct value gets a whole directory, and (depending on
how you write) potentially its own file per write pass. Think about what
"month" (18 values, known upfront, roughly evenly sized) buys you versus a
column with hundreds of values, most of them touched by only a handful of
rows. What does "one file per partition" versus "one file per (partition,
write-chunk)" do to file count as chunk count grows?

Before writing any code, go count the actual distinct values of a couple of
candidate columns in your own `data/raw`. Don't guess — the answer changes
which column is "the trap" and which is "the sane choice," and the numbers
in this task's README are for the reference dataset, not necessarily yours.
