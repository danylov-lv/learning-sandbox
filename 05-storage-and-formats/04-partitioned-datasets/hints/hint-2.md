# Hint 2

`pyarrow.dataset.write_dataset(table_or_batches, base_dir, partitioning=...,
format="parquet", existing_data_behavior=...)` is the tool. A few things
that matter:

- `partitioning` can take a list of column names (pyarrow infers hive-style
  layout from them) or an explicit `ds.partitioning(schema, flavor="hive")`.
  Either works for a single string partition column like `month` or
  `category`.
- What you pass as the *input* controls file count more than any writer
  option does. Pass one big table for a partition and you tend to get one
  file for that partition. Call `write_dataset` once per small chunk as you
  stream, and you get one (or more) new files per chunk, per partition
  touched by that chunk — multiplied across however many chunks you process.
  That is the entire mechanism behind the small-files trap: it is not a
  misconfiguration, it is what naive streaming writes do by default.
- `existing_data_behavior="overwrite_or_ignore"` lets you call
  `write_dataset` multiple times into the same base directory without
  erroring, but if you don't vary the file naming between calls you can
  silently clobber earlier output instead of accumulating it. Check what the
  default `basename_template` does across repeated calls.
- For the month lake, think in terms of accumulation: buffer rows per
  partition key up to some bounded size, sort that buffer, write it as one
  file, clear it, keep going. That gives you both "few files per partition"
  and "bounded memory" without ever holding the whole dataset (or even one
  whole month, if a month is large) resident forever.
- Sorting only helps a reader if it survives to disk *inside* the file that
  gets opened. If a partition ends up as more than one file, each file
  should be internally sorted by the key even if the files don't merge into
  one global order — a reader pruning by row-group/page statistics only
  cares about the file it actually opened.
