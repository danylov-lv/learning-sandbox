# 07 -- DuckDB vs ClickHouse

## Backstory

You have the same 180 days of scraped price history in two places at once:
landed in a running ClickHouse server (`price_history.observations_raw`, the
MergeTree from task 01) and sitting as Parquet files on disk (the
Hive-partitioned lake from task 06, `data/parquet/category=<x>/part-0.parquet`).
Nobody deleted either copy -- they're deliberately kept coherent so this task
can ask the question those two tasks set up but never answered directly: for
the SAME query, on the SAME data, is the server worth having?

ClickHouse is a long-lived process. Something started it, something patches
it, something pages you if it falls over, and every query pays a network
round trip to reach it. DuckDB, queried the way task 06 used it, is not a
process at all in that sense -- it's a library that opens files, scans them,
and exits when your script does. No daemon, no ops burden, no protocol
overhead -- but also nothing cached from the last query, no concurrent
users to serve, no background merges keeping the on-disk layout tidy.

This task times both, on purpose, on your own machine, and asks you to look
at the number instead of assuming which one "obviously" wins. The answer
depends on scale and on what else the query has to share the machine with --
which is exactly why the timing here is relative, not a rule to memorize.

## What's given

- `src/bench.py` -- two functions, each returning `{category: (count,
  avg_price)}` for the per-category, in-stock-only aggregate:
  - `ch_answer(client)` -- queries `observations_raw` through a live
    clickhouse-connect client.
  - `duck_answer(con)` -- queries the Parquet lake through a live in-memory
    DuckDB connection, via `read_parquet(parquet_glob(), hive_partitioning=
    true)`.
  Both currently `raise NotImplementedError`. Rich docstrings on each explain
  exactly what to query and what shape to return.
- The live stack: ClickHouse HTTP on `localhost:8309` (db `price_history`,
  user/password `sandbox`/`sandbox`), and the Parquet lake under
  `data/parquet/`. `harness/common.py` gives you `ch_client()`, `ch_query()`,
  `duckdb_connect()`, `parquet_glob()`, `time_it()`, `write_baseline()`,
  `read_baseline()`.
- `data/ground-truth.json`, the committed answer key (`per_category_instock`
  -- see the module README for how it's kept coherent with whatever scale
  the stack is currently loaded at).
- `baseline.py` -- times both functions once implemented, prints
  `ch_seconds`, `duck_seconds`, and their ratio, and records them to a
  gitignored `baseline-local.json`.

## What's required

Implement both functions in `src/bench.py`. Each computes the aggregate
IN THE ENGINE (SQL `GROUP BY` / `avg`), not by pulling raw rows into Python
and averaging them yourself -- that would make the timing comparison
meaningless, since you'd be timing your own Python loop, not the engine.

Try it by hand before trusting the validator:

```bash
uv run python baseline.py
uv run python tests/validate.py
```

## Completion criteria

Run, from this task's directory:

```bash
uv run python tests/validate.py
```

It:

- Runs `ch_answer()` and `duck_answer()` and checks EACH against
  `data/ground-truth.json`'s `per_category_instock`: every category's count
  exact, average within a small rounding tolerance, category set matching
  exactly (no missing/extra from either engine). **This is the primary,
  hard gate** -- a fast wrong answer fails, from either engine.
- Asserts the two engines AGREE WITH EACH OTHER within the same tolerance.
  Both read the same underlying corpus, so if `ch_answer()` and
  `duck_answer()` disagree, something is broken regardless of what ground
  truth says -- that agreement check is the actual point of this task: same
  data, same answer, different engine.
- Times both functions, writes the timings to a gitignored
  `baseline-local.json`, and prints `ch_seconds`, `duck_seconds`, and the
  ratio. **Timing is recorded, not gated** -- there is no hard threshold on
  the ratio. At the ~500k-row local scale used for verification, the two
  engines can land close together, or even flip which one is faster from run
  to run (see "A note on the numbers" below) -- that instability is itself
  informative, not a bug in the task.
- Fails cleanly (`NOT PASSED: <reason>`, exit 1, no traceback) if the stack
  is down, the Parquet lake is missing, either function still raises
  `NotImplementedError`, either function's answer is wrong, or the two
  engines disagree beyond tolerance.

## A note on the numbers

During authoring, at SCALE=0.01 (500k rows), repeated runs put ClickHouse
around 0.06s and DuckDB anywhere from 0.01s (warm OS file cache) to 0.23s
(the very first query in a cold process) -- the ratio swung from "ClickHouse
4x faster" to "DuckDB 4x faster" between runs on the same machine, same
data, same code. Neither number tells you much on its own at this scale:
network/HTTP overhead to a local ClickHouse container and file-open/schema
overhead for eight small Parquet files are both small enough that whichever
happens to be warmer wins. The real gap this comparison is built to reveal
shows up at 50M+ rows (task 05's territory) and under concurrent load,
where ClickHouse's persistent process -- caches held across queries, a
storage engine already tuned by background merges, many users sharing one
warm working set -- starts to matter, and where DuckDB pays the full
Parquet-scan cost on every single invocation with nothing carried over.
Record what you actually see on your machine; don't expect it to match
these numbers exactly, and don't expect it to be stable across repeated
runs at this scale either.

## Estimated evenings

1

## Topics to read up on

- Server vs embedded (in-process) OLAP engines: what a "server" buys you
  (a persistent working set, concurrency, one place to secure/monitor) and
  what it costs (a process to run, patch, and pay for, a network hop per
  query)
- ClickHouse MergeTree vs DuckDB-on-Parquet as two different answers to
  "how do I query a columnar dataset fast"
- Why relative, machine-local benchmarking (a baseline file, a ratio) is the
  only honest way to compare two engines' timing -- and why a single
  absolute number from someone else's laptop is close to meaningless
- What changes between "500k rows, one query, one user" and "50M rows,
  many queries, many users" -- concurrency, ingest rate, and working-set
  size are usually the reasons a server earns its keep, not raw scan speed
  alone

This task sets up task 08 (`when-clickhouse-when-duckdb`), a written task
that asks you to argue the tradeoff explicitly using what you measured here
and in task 05.

## Off-limits

`.authoring/` (at the module root) holds the full data contract, RNG draw
order, and design rationale for every task in this module -- spoilers.
Don't read it before finishing this task.
