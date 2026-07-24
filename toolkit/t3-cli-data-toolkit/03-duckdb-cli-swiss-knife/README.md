# 03 — DuckDB CLI as a Swiss Knife

## Backstory

A warehouse export landed as a directory of Parquet files (one per
category, hive-partitioned) plus a small CSV dimension table mapping each
product to its region. Spinning up a server or writing a Python script for
three one-off questions would be overkill — the DuckDB CLI queries the
files directly, no loading step, no server. This is the "swiss knife"
workflow: `duckdb -json -c "..."` straight against files on disk.

## What's given

- `data/warehouse/parquet/category=<cat>/part-0.parquet` — one file per
  category. Columns: `product_id`, `ts` (an ISO-ish timestamp string,
  lexicographically sortable), `price` (float). `category` is **not** a
  column inside the files — it's a hive partition directory, exposed only
  when you read with `hive_partitioning=true`.
- `data/warehouse/products.csv` — columns `product_id`, `category`,
  `region`, `listed_at`. One row per product (120 of them); `region` is
  one of `us-east`, `us-west`, `eu-west`, `eu-central`, `apac`.
- `src/solve.sh` — a stub that currently just exits 1. Fill it in with
  three `duckdb -json -c "..."` invocations, printed as three labeled
  JSON blocks (exact format below).
- `tests/validate.py` — the validator.
- `hints/` — three tiers of hints.

Run `uv run python generate.py` from the module root first if `data/`
doesn't exist yet.

**Windows/Git Bash note**: `duckdb` here is a native Windows binary, not
an MSYS one — it does not understand a POSIX-style path like
`/d/Programming/...`. If you build a path in your script with `` `pwd` ``
from Git Bash, use `` `pwd -W` `` instead (or just write the path
relative to wherever you invoke `duckdb` from) so DuckDB gets a
`D:/...`-style path it can actually open.

## What's required

Make `src/solve.sh` print exactly this shape to stdout — three sections,
each an `===Qn===` marker line followed by one JSON array (i.e. the raw
output of `duckdb -json -c "..."`, one call per section):

```
===Q1===
[{"category": ..., "obs_count": ..., "avg_price": ...}, ...]
===Q2===
[{"region": ..., "obs_count": ..., "avg_price": ...}, ...]
===Q3===
[{"product_id": ..., "jump_ts": ..., "jump_amount": ...}, ...]
```

**Q1 — aggregate over a glob.** Read the whole Parquet directory in one
`read_parquet(..., hive_partitioning=true)` call (a glob over
`data/warehouse/parquet/**/*.parquet`, not per-category files by hand).
For each `category`, report `obs_count` (row count) and `avg_price` (mean
of `price`) across *every* observation of every product in that category.
Array order does not matter.

**Q2 — join the CSV to the Parquet.** Join `products.csv` to the Parquet
observations on `product_id` to pull in `region`. For each `region`,
report `obs_count` and `avg_price` across every observation of every
product in that region. Array order does not matter.

**Q3 — a window function.** For each `product_id`, using
`LAG(price) OVER (PARTITION BY product_id ORDER BY ts)`, compute the
single-step change `delta = price - LAG(price)` at every observation
after the first (the first observation per product has no `LAG` and is
excluded). Find the observation with the **largest** `delta` for that
product — this is the biggest one-step jump, and it can be negative if a
product's price only ever fell. Report `jump_ts` (that observation's
`ts`) and `jump_amount` (that `delta`), one row per product (all 120
products must appear). **Tie-break**: if two observations for the same
product share the exact maximum delta, report the one with the earlier
`ts`. Array order does not matter.

## Completion criteria

Run, from the module root:

```bash
cd toolkit/t3-cli-data-toolkit
uv run python generate.py   # once, if data/ doesn't exist yet
uv run python 03-duckdb-cli-swiss-knife/tests/validate.py
```

The validator runs `src/solve.sh`, parses the three `===Qn===` JSON
blocks, and compares each against an independent recomputation performed
in Python (pandas over the same files, not a re-run of your SQL) with a
numeric tolerance on the float columns. Prints `PASSED` or
`NOT PASSED: <reason>`.

## Estimated evenings

1

## Topics to read up on

- Hive-partitioned directory layout and `hive_partitioning=true` in
  `read_parquet`
- Glob patterns in DuckDB's file-reading functions (`**/*.parquet`)
- `read_csv` auto-detection vs an explicit schema
- Window functions: `PARTITION BY`, `ORDER BY` inside `OVER (...)`, and
  `LAG`/`LEAD`
- Filtering down a window result with `QUALIFY` vs a wrapping CTE/subquery
- DuckDB's `-json` output mode vs its default box-drawing table mode

## Off-limits

`.authoring/` (at the module root) documents this module's grading
contract, not a solution — there are no reference solutions anywhere in
this repository. Read it after finishing this task, if at all.
