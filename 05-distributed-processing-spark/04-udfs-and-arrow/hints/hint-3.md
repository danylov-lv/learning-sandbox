`prepare_events`: `spark.read.json(str(jsonl_dir / "*.jsonl"))`, then `.filter(F.col("_corrupt_record").isNull()).drop("_corrupt_record")`, then `.distinct()`, then `.filter(F.col("http_status") == 200)`, then `.select("product_id", "source_id", "price", "attrs")`.

`with_python_udf` shape:

```python
result_schema = T.StructType([
    T.StructField("weight_g", T.DoubleType()),
    T.StructField("bucket", T.StringType()),
])

def compute(price, attrs):
    # pull weight_g out of attrs defensively; apply the bucket rule
    ...
    return (weight_g, bucket)

udf = F.udf(compute, result_schema)
out = events_df.withColumn("derived", udf(F.col("price"), F.col("attrs")))
# then split out["derived"]["weight_g"] / out["derived"]["bucket"] into top-level columns
```

`with_pandas_udf` shape: extract weight_g first —

```python
staged = events_df.withColumn("weight_g_raw", F.col("attrs")["weight_g"].cast("double"))

@F.pandas_udf(result_schema)
def compute(price: pd.Series, weight_g: pd.Series) -> pd.DataFrame:
    # vectorized bucket logic over the whole Series — no per-row loop
    ...
    return pd.DataFrame({"weight_g": weight_g, "bucket": bucket})

out = staged.withColumn("derived", compute(F.col("price"), F.col("weight_g_raw")))
```

`with_builtins` shape: no Python callable at all. Pull the weight straight off the struct column (`F.col("attrs")["weight_g"]` with a cast, same as the pandas staging step above) and express the bucket rule as a `F.when(...).when(...).otherwise(...)` chain — one branch per case from the README's bucket definition, null check first, threshold order matters. Two `withColumn` calls and you are done; if your plan for this variant shows any `*EvalPython` node, something in the chain still calls Python.

For the bench/validate timing gap to show up clearly, make sure `tests/bench.py`'s cache-warming `.count()` actually runs before any of the three timed writes (it does, in the provided script) — timing an uncached read would mix I/O variance into the comparison you're trying to isolate.
