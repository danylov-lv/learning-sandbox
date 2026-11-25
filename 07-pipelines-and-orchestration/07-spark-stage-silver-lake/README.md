# 07 — Spark stage: silver lake

## Backstory

The analytics team is done querying raw NDJSON through ad-hoc scripts. They want a columnar lake: a "silver" layer in object storage — parseable, deduplicated, partitioned by day — that notebooks and downstream jobs can read without re-litigating JSON parsing every time. Meanwhile your row-by-row psycopg transform has quietly become the slowest stage in the pipeline; at tens of thousands of records a day it still works, but the team has already been told volume is going to 10x.

You know Spark from the previous module. The new part is operational: running a Spark job *as a pipeline stage*, owned and scheduled by Airflow, idempotent per partition like everything else in this module. This stack bakes the JRE, pyspark, and the s3a jars straight into the Airflow image, so the job runs in local mode inside the Airflow container — one of several legitimate ways to marry Airflow and Spark, and you'll be asked to argue about the alternatives, not just code this one.

## What's given

- `src/t07_spark_lake.py` — DAG skeleton. Copy it into the module's `dags/` directory and fill in the TODOs.
- `dags/smoke_env.py` (module level) — a known-good SparkSession-against-MinIO configuration for this exact image: endpoint, credentials, path-style access. Start from it; do not rediscover s3a config by trial and error.
- The raw dumps `data/raw/dt=2025-06-01..14/` mounted at `/opt/sandbox/data` inside the containers, and the `lake-06` bucket in MinIO (host port 9601, console 9602).
- `tests/validate.py` — the validator.
- `NOTES.md` — contains a required section you must write (see below).

## What's required

**1. The DAG.** `t07_spark_lake`, one Spark stage that builds one day's silver partition:

- Read `/opt/sandbox/data/raw/dt=<ds>/prices.ndjson` with Spark's JSON reader, configured to *tolerate* corrupt lines: the raw dumps contain ~0.4% unparseable garbage, and the job must neither crash on it nor let it slip through as all-null rows you can't distinguish from real data. Spark has a documented mechanism for exactly this; finding and correctly using it is part of the task (there is a well-known gotcha when filtering on its output right after reading — the error message will point you at the fix).
- Drop the corrupt rows and drop exact duplicate rows. The dumps contain byte-identical repeated lines (~2%); identical lines parse to identical rows.
- Do **not** apply task 04's business-rule validation here. This stage is structural cleanup only: invalid-but-parseable records (bad prices, unknown currencies, ...) stay in silver. Warehouse quarantine and lake cleanup are different concerns with different owners.
- Write parquet to `s3a://lake-06/silver/prices/dt=<ds>/`, overwriting **that partition only**: rerunning a day replaces its files byte-for-byte-equivalent in content, never appends, never touches neighboring days.
- The corrupt-record bookkeeping column must not appear in the written schema.
- Missing input directory for the day → the task fails.
- Spark runs `local[*]` (or `local[2]`) inside the Airflow container; build the session like `smoke_env.py` and stop it in `finally`.

Run it for three days that between them cover both schema-drift regimes:

    docker compose exec airflow-scheduler airflow dags test t07_spark_lake 2025-06-01
    docker compose exec airflow-scheduler airflow dags test t07_spark_lake 2025-06-10
    docker compose exec airflow-scheduler airflow dags test t07_spark_lake 2025-06-14

(2025-06-10 gains a `seller_rating` column; on 2025-06-14 `price` arrives as a string. Per-day schemas will differ across partitions — that is expected and fine for this task.)

**2. The write-up.** Embedding Spark local-mode inside the orchestrator's own container is a real pattern, but it is one of four. In `NOTES.md`, under the pre-created `## Operator comparison` heading, write a comparison of:

- embedded local-mode pyspark inside the Airflow worker/container (what you just did),
- `SparkSubmitOperator` against an external Spark cluster,
- `DockerOperator` running the job in its own container image,
- `KubernetesPodOperator`.

When is each the right call? Think resource isolation, dependency/image management, who owns the JVM, data locality, failure semantics and retries, dev-loop speed, and what changes at 10x volume. At least three substantive paragraphs; the validator checks length and that all four options are actually discussed, and no, it cannot check insight — that part is for you.

## Completion criteria

From this task directory, with the compose stack up:

    uv run python tests/validate.py

prints `PASSED`. The validator:

- reads MinIO from the host and checks, for each of the three days, that the partition `silver/prices/dt=<day>/` exists and its row count equals `parseable_records - duplicate_lines` from ground truth (the identity for "parseable, exact-duplicates removed" — equivalently `valid_records + invalid_records.total`);
- checks no column with "corrupt" in its name survived into any partition's schema;
- reruns 2025-06-01 itself via `airflow dags test` and checks the partition row count is unchanged (overwrite, not append);
- checks the `## Operator comparison` section of `NOTES.md` mentions all four execution options and contains at least three paragraphs of at least 300 characters each.

## Estimated evenings

1

## Topics to read up on

- Spark JSON data source read modes (PERMISSIVE / DROPMALFORMED / FAILFAST) and corrupt-record handling
- Why filtering on the corrupt-record column requires materialization (caching) first
- `dropDuplicates` vs `distinct` and their semantics with null columns
- Parquet write modes and partition-scoped overwrite strategies (path-targeted writes vs dynamic partition overwrite)
- Running Spark in local mode: what `local[*]` actually gives you and what it doesn't
- Airflow patterns for launching Spark: SparkSubmitOperator, DockerOperator, KubernetesPodOperator
- s3a filesystem configuration and committers against S3-compatible stores
