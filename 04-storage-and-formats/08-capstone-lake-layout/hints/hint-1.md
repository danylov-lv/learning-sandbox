# Hint 1 — turning measurements into a layout

You already have every number you need; the work here is deciding, not
discovering. Before writing any code, go back through tasks 01-07 and
build yourself a small decision matrix: one row per layout axis, one
column for "what I measured," one for "what it implies for the capstone."

- **Format** (task 01): you measured Parquet's size ratio against raw
  JSONL and the column-read speedup. That number is your argument for
  "Parquet, not JSONL or CSV, full stop" — you don't need to re-litigate
  it, just cite it.
- **Codec** (task 02): you measured size and write/read time across
  snappy/gzip/zstd at multiple levels. The capstone asks for zstd
  specifically — your job is to know *why*, with the number, not to
  re-pick a codec.
- **Row group size** (task 03): you measured how row-group size trades off
  against pruning selectivity and per-file overhead. This capstone's
  pruning gate is a direct descendant of that measurement — the row-group
  size you found effective there is a strong starting point here, not a
  fresh guess.
- **Partitioning** (task 04): you built a hive-partitioned lake and also
  saw the high-cardinality trap. The capstone's partition key (month) is
  given, but your task-04 numbers on partition count vs. file count vs.
  query pruning tell you how aggressively to also sort *within* a
  partition rather than partitioning more finely.
- **Object storage** (task 05): your LIST latency numbers are the reason
  file-count ceilings matter at all on this layout — a rule like "no more
  than 8 files per partition" is not arbitrary, it is downstream of a
  request-cost number you already have.
- **Table format** (task 06): Delta's transaction log solved a class of
  problems (atomic multi-file commits, time travel, schema evolution)
  that a bare hive-partitioned Parquet lake does not solve. Knowing
  exactly which problems it solved — and which of today's gates you are
  enforcing by hand instead — is most of CP3's last section.
- **Query engine** (task 07): the pushdown you saw in DuckDB's query plans
  is the same mechanism CP2's pruning gate is testing, just from the
  other side (you built the row groups instead of reading someone else's).

Once that matrix exists, the pipeline in CP1 is mostly mechanical —
you're implementing decisions you already defended to yourself with
numbers, not exploring the design space from scratch.
