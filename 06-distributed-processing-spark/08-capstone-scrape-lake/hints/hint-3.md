# Hint 3 — concrete approach per checkpoint

## CP1 — `build_silver`

1. `raw = spark.read.json(str(jsonl_dir / "*.jsonl"))`; `valid =
   raw.filter(F.col("_corrupt_record").isNull()).drop("_corrupt_record")`;
   `deduped = valid.distinct()`.
2. `sources = spark.read.option("header", True).option("inferSchema",
   True).csv(str(reference_dir / "sources.csv"))`, same for
   `categories.csv`.
3. `spark.conf.set("spark.sql.adaptive.enabled", "false")` before building
   the joins you're about to capture a plan on.
4. `joined = deduped.join(F.broadcast(sources), "source_id").join(F.broadcast(categories), "category_id")`.
5. `plan = get_plan(joined, "formatted")` — do this now, before adding
   `month` or repartitioning, so it's the plan the validator expects.
6. `enriched = joined.withColumn("month", F.substring(F.col("captured_at"), 1, 7))`.
7. `enriched.repartition("month").write.mode("overwrite").partitionBy("month").parquet(dest)`
   — or `repartition(N, "month")` if you want more than one file per
   month at larger scale; N should stay small (a handful, not hundreds)
   relative to how many rows a month actually holds.
8. Read `dest` back (`spark.read.parquet(dest)`) to build `total_rows`
   and `rows_by_month` for your return dict — simplest to reason about
   since it's exactly what got written, same approach task 06 suggests.
9. Return `{"plan": plan, "total_rows": ..., "rows_by_month": {...}}`.

## CP2 — `run_naive` / `run_tuned`

Both functions share this shape; only the config block and the
broadcast hint differ:

```
spark.conf.set(...)   # config block, different per function — see docstrings
s = spark.read.parquet(silver_dest).filter(F.col("http_status") == 200)
a = s.filter(F.col("month") == MONTH_A).groupBy("product_id", "source_id").agg(F.avg("price").alias("avg_price_a"))
b = s.filter(F.col("month") == MONTH_B).groupBy("product_id", "source_id").agg(F.avg("price").alias("avg_price_b"))
joined = a.join(b, ["product_id", "source_id"]).withColumn("delta", F.col("avg_price_b") - F.col("avg_price_a"))
region_dim = spark.read.option("header", True).option("inferSchema", True).csv(str(reference_dir / "sources.csv")).select("source_id", "region")
# run_tuned only: region_dim = F.broadcast(region_dim)
result = joined.join(region_dim, "source_id").groupBy("region").agg(
    F.sum("delta").alias("sum_delta"), F.avg("delta").alias("avg_delta"), F.count(F.lit(1)).alias("n")
)
return result
```

`run_naive`: `adaptive.enabled=false`, `shuffle.partitions=200`,
`autoBroadcastJoinThreshold=-1` (not the 10MB default — see the module
docstring for why this task forces it rather than relying on the
heuristic), no broadcast hint on `region_dim`.

`run_tuned`: `adaptive.enabled=true`, `shuffle.partitions` set to
something you picked deliberately (count the distinct `(product_id,
source_id)` pairs in one month's slice first — `s.filter(month ==
MONTH_A).select("product_id", "source_id").distinct().count()` — and
reason from there, don't just guess a small number),
`autoBroadcastJoinThreshold=10485760` (reset it — if you skip this and
`run_naive` already ran on the same session, the threshold is still `-1`
and AQE will not convert the step-3 join to broadcast at runtime, even
though `region_dim`'s explicit hint still works), `region_dim` wrapped in
`F.broadcast(...)`.

`reference_dir` for the region dimension can be a module-level constant
pointing at `/workspace/data/reference` inside the container, or a
parameter you thread through — your call, the contract only fixes the
function signature `run_naive(spark, silver_dest)` /
`run_tuned(spark, silver_dest)`.

For `tests/bench.py`, nothing to implement — just run it after both
functions work, and watch `localhost:4040` while `naive_df.write.format("noop")...`
and then `tuned_df.write.format("noop")...` each run, one at a time.
