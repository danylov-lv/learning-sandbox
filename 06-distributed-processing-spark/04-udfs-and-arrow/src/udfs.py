"""Three ways to compute the same two derived columns over PriceWatch's clean events.

PriceWatch needs, on every clean snapshot:
  - `weight_g`: a double, pulled out of the messy nested `attrs` payload
    (attrs.weight_g, itself sometimes missing or non-numeric).
  - `bucket`: a price bucket string — "unknown" if price is null, "low" if
    price < 20, "mid" if 20 <= price < 100, "high" if price >= 100.

A teammate shipped this as a plain Python UDF (`with_python_udf`) and
throughput cratered on the full dataset. This task has you implement the
same transformation three ways and measure what each one actually costs:

  1. with_python_udf   — a plain `pyspark.sql.functions.udf`, one Python
     function call per row, no Arrow involved.
  2. with_pandas_udf   — a `pandas_udf`, same logic, but Spark hands whole
     Arrow-backed pandas Series across the JVM/Python boundary in batches
     instead of one row at a time.
  3. with_builtins     — no Python row code at all: pure Catalyst
     expressions (`when`/`otherwise`, struct field access, casts). Catalyst
     can see straight through this and optimize/fuse it like any other
     expression, unlike the two UDF variants which are opaque black boxes
     to the optimizer.

All three functions take the *same* input DataFrame (produced by
`prepare_events`) and must return the *same* columns, so the validator can
call them interchangeably and compare results.

Every function that measures a plan or a partition count elsewhere in this
module would need AQE disabled first; that concern does not apply here —
the plan-node checks in this task (`BatchEvalPython` / `ArrowEvalPython`)
survive AQE because they come from a per-partition Python eval node, not a
shuffle-partition count. You do not need to touch `spark.sql.adaptive.*`
in this task.
"""

from pathlib import Path


def prepare_events(spark, jsonl_dir: Path):
    """Build the shared input DataFrame the three variants below all consume.

    Read every *.jsonl file under jsonl_dir, then:
      1. Drop rows where the JSON failed to parse (`_corrupt_record` is not
         null) and drop the `_corrupt_record` column itself.
      2. Deduplicate exact retry-storm repeats: whole-row `.distinct()`.
      3. Keep only rows where `http_status == 200` (price/in_stock are only
         meaningful, non-null, on a successful scrape).
      4. Select exactly the columns the three variants need:
         `product_id`, `source_id`, `price`, `attrs`.

    Returns:
        a DataFrame with columns (product_id, source_id, price, attrs) —
        `attrs` stays as the original nested struct column; extracting
        `weight_g` from it is each variant's own job, not this function's.
    """
    raise NotImplementedError("implement prepare_events")


def with_python_udf(spark, events_df):
    """Derive weight_g and bucket with a plain Python UDF (pyspark.sql.functions.udf).

    Write a single Python function that takes a row's `price` (float or
    None) and `attrs` (a Row/dict-like or None, whose `weight_g` field may
    be missing, null, or non-numeric) and returns a (weight_g, bucket)
    tuple matching the bucket rule in this module's docstring. Wrap it with
    `F.udf(...)` against a StructType(weight_g: double, bucket: string),
    apply it in a single `withColumn`, then split the resulting struct
    column into two top-level columns.

    Every row's (price, attrs) pair is pickled from the JVM, sent to a
    Python worker process, unpickled, run through your plain Python
    function one row at a time, and the result pickled back — this
    round trip is what the validator's plan check and the timing gate in
    tests/bench.py are measuring the cost of.

    Returns:
        a DataFrame with columns (product_id, source_id, price, weight_g,
        bucket).
    """
    raise NotImplementedError("implement with_python_udf")


def with_pandas_udf(spark, events_df):
    """Derive weight_g and bucket with a pandas_udf (Arrow-backed).

    Same output contract as with_python_udf, but implemented as a
    `pandas_udf` (Arrow-vectorized): your function receives whole pandas
    Series (a batch of rows' `price` values, and a batch of already
    Arrow-extracted `weight_g` values — see below) at once, computes the
    bucket with vectorized pandas/numpy operations (no per-row Python
    loop), and returns a pandas DataFrame/Series matching the declared
    result schema.

    Struct-returning pandas UDFs need a plain, JVM-side value for each
    input column — extract `attrs.weight_g` as its own double column with
    `withColumn` (a Catalyst struct-field access, not part of the UDF)
    *before* calling the pandas_udf, and pass that column in as one of the
    UDF's Series arguments alongside `price`. This keeps the UDF itself
    free of any per-row struct-drilling.

    Returns:
        a DataFrame with columns (product_id, source_id, price, weight_g,
        bucket) — same shape and same values as with_python_udf.
    """
    raise NotImplementedError("implement with_pandas_udf")


def with_builtins(spark, events_df):
    """Derive weight_g and bucket with no Python row code at all.

    Use Catalyst built-ins only:
      - `weight_g`: direct struct field access on the `attrs` column
        (`col("attrs")["weight_g"]`), cast to double.
      - `bucket`: a `when(...).when(...).otherwise(...)` chain implementing
        the same rule as the other two variants (null price -> "unknown",
        < 20 -> "low", < 100 -> "mid", else -> "high").

    No `udf`/`pandas_udf` anywhere in this function. Every expression here
    is something Catalyst's optimizer can see into, reorder around, and
    (on a columnar source) push down or fuse — none of that is possible
    once a plain or pandas UDF sits in the plan as an opaque node.

    Returns:
        a DataFrame with columns (product_id, source_id, price, weight_g,
        bucket) — same shape and same values as the other two variants.
    """
    raise NotImplementedError("implement with_builtins")
