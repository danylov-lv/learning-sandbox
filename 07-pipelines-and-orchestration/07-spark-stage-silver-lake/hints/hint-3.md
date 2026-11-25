# Hint 3

The whole task, as pseudocode:

```
build_silver_partition(dt = the run's logical date):
    in_path = raw dir / dt=<dt> / prices.ndjson
    if the file does not exist -> raise (the run must FAIL)

    build the SparkSession exactly as smoke_env.py does
    (s3a endpoint/creds/path-style), master local[*]
    try:
        read the file with the JSON reader in PERMISSIVE mode,
        naming a corrupt-record column so unparseable lines are
        kept as rows whose only non-null field is that column

        if the corrupt column is present in the schema:
            materialize the DataFrame (cache) -- this is the fix for
                the AnalysisException described in hint 2
            keep only rows where the corrupt column is null
            drop the corrupt column

        whole-row dedup (dropDuplicates with no column list)

        write parquet, overwrite mode, target path
        s3a://lake-06/silver/prices/dt=<dt>
    finally:
        stop the session
```

Why the pieces are ordered this way:

- The "if the corrupt column is present" guard: with an inferred schema the column only appears when the file actually contains corrupt lines. Every committed day does, but the guard keeps the job correct on clean inputs too.
- Caching before the filter is what turns "query only internal corrupt-record data" (disallowed) into "query materialized parsed rows" (fine).
- Whole-row dedup runs after the corrupt column is gone, so it compares only real data columns. Byte-identical input lines parse to identical rows, so it removes exactly the planted duplicate lines — which is why the validator's expected count is `parseable_records - duplicate_lines`.
- Overwrite mode against the explicit `dt=<day>` path gives per-partition idempotency with no extra configuration: Spark clears that prefix and writes fresh part files, and other days' prefixes are simply never in scope. No dynamic-partition-overwrite settings needed.

The expected row counts, if you want to check yourself before running the validator: 37805 for 2025-06-01, 30269 for 2025-06-10, 36546 for 2025-06-14 (each `= parseable_records - duplicate_lines` from `data/ground-truth.json`).

For the write-up, the axes that make the comparison substantive: where the JVM lives and whose memory/CPU budget it consumes (embedded = inside the Airflow container, competing with the scheduler); how dependencies ship (baked image vs spark-submit `--py-files`/`--packages` vs a per-job image); blast radius of an OOM; whether a retry restarts a whole cluster application or one pod/container; and what each option costs to iterate on. Embedded local mode wins the dev loop and loses isolation; SparkSubmitOperator presumes a cluster someone operates; DockerOperator isolates dependencies but still spends one host's resources; KubernetesPodOperator buys elasticity and isolation at the price of running a k8s platform and a slower feedback loop.
