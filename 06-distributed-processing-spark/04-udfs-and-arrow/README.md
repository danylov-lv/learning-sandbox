# 04 — UDFs and Arrow

## Backstory

PriceWatch needs two derived columns on every clean snapshot: `weight_g`, pulled out of the messy nested `attrs` payload, and a price `bucket` ("unknown" if price is null, "low" under 20, "mid" under 100, "high" otherwise). A teammate shipped it as the obvious thing — a plain Python function wrapped in `F.udf` — and it worked, and it was correct, and throughput on the full dataset cratered compared to everything else in the pipeline. Nobody could say by how much, or why, beyond "UDFs are slow," which isn't an explanation you can act on.

You're going to implement the same transformation three ways and measure, not guess: a plain Python UDF (one Python function call per row, with the corresponding serialize/deserialize tax), a `pandas_udf` (Arrow-vectorized — Spark hands your function whole columns at once instead of one row at a time), and built-in Catalyst expressions (no Python row code at all). Then you look at the actual query plans and the actual wall-clock numbers on this machine, so "UDFs are slow" turns into "here is what's slow about them, here is what fixes how much of it, and here is what the real answer looks like."

## What's given

- `data/raw-events/*.jsonl` and `data/ground-truth.json` (same dataset as the other tasks in this module).
- `src/udfs.py` — four function signatures, fully documented, all raising `NotImplementedError`.
- `tests/bench.py` — **fully implemented, not yours to edit.** Imports your `src/udfs.py`, times each variant with a `noop`-format write (forces full materialization without paying for `collect()` or real I/O), and writes `results-local.json`. This *is* part of what `validate.py` gates on here (unlike task 02's `bench.py`, which was purely informational) — the timing numbers come from your implementation, run on your machine.
- `tests/validate.py` — the validator (runs in-container, needs a live SparkSession).

## What's required

Implement all four functions in `src/udfs.py`:

1. **`prepare_events(spark, jsonl_dir)`** — the shared input all three variants consume: drop corrupt/unparseable lines, deduplicate exact retry-storm repeats, keep `http_status == 200` rows, select `product_id`, `source_id`, `price`, `attrs`.
2. **`with_python_udf(spark, events_df)`** — a plain `pyspark.sql.functions.udf` returning a `weight_g`/`bucket` struct, split into two columns.
3. **`with_pandas_udf(spark, events_df)`** — the same logic as a `pandas_udf`: your function receives batches of rows as pandas Series and computes the result with vectorized pandas operations, not a per-row Python loop.
4. **`with_builtins(spark, events_df)`** — the same result with zero UDFs: struct field access, casts, and a `when`/`otherwise` chain.

Full docstrings with exact column-name contracts are in `src/udfs.py` — the three transformation functions must all take the same input shape and return the same output shape, because the validator calls them interchangeably.

Then run (from the module root):

```bash
./run.sh 04-udfs-and-arrow/tests/bench.py       # times your three variants, writes results-local.json
./run.sh 04-udfs-and-arrow/tests/validate.py    # the actual gate
```

Watch `localhost:4040` while `bench.py` runs if you want to see the stage/task breakdown for each variant.

Fill in `NOTES.md`: the three wall times, the two ratios, which plan nodes you actually saw for each variant (`BatchEvalPython`, `ArrowEvalPython`, or neither), and what you think accounts for the pandas_udf-vs-plain-udf gap specifically (it isn't "no serialization" — Arrow still crosses the JVM/Python boundary; work out what's actually different).

## Completion criteria

`tests/validate.py` prints `PASSED`. It checks:

- **Plan structure**: `with_python_udf`'s plan contains `BatchEvalPython` and not `ArrowEvalPython`; `with_pandas_udf`'s plan contains `ArrowEvalPython` and not `BatchEvalPython`; `with_builtins`'s plan contains neither.
- **Correctness**: all three variants produce an identical aggregate fingerprint (row count per bucket, plus a rounded count/sum of `weight_g`), and that fingerprint matches a reference the validator computes independently with its own built-in-only Spark code — not by calling your `with_builtins`.
- **Timing**: `results-local.json` exists (written by `tests/bench.py`) and `python_udf_seconds / builtins_seconds` clears a floor measured to have generous slack under this machine's actual gap, and likewise `python_udf_seconds / pandas_udf_seconds`.
- `NOTES.md` has real content.

## Estimated evenings

1

## Topics to read up on

- Python UDF serialization cost: pickling driver-side closures, per-row round trips across the JVM/Python boundary
- Arrow columnar transfer and why batching amortizes the boundary crossing that `pandas_udf` still has to make
- `pandas_udf` type signatures: Series-to-Series, Series-to-struct, and what shape of function each expects
- Why an opaque UDF (plain or pandas) is a Catalyst optimization barrier — what the optimizer can and can't see through it
- `get_json_object` / `from_json` as alternatives when the payload really is a JSON string rather than an already-typed struct
- `when`/`otherwise` chains vs `CASE WHEN`, and struct field access on a nested column
