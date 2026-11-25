"""t07_spark_lake — skeleton.

Copy this file into the module's dags/ directory before running it:

    cp src/t07_spark_lake.py ../dags/

Then iterate with:

    docker compose exec airflow-scheduler airflow dags test t07_spark_lake 2025-06-01

The Airflow image has a JRE, pyspark 3.5, and the hadoop-aws/s3a jars baked
in — Spark runs in local[*] mode inside the airflow container, no cluster
involved. dags/smoke_env.py shows the exact SparkSession + s3a-against-MinIO
configuration that is known to work in this stack.

Raw input (inside the container): /opt/sandbox/data/raw/dt=<ds>/prices.ndjson
Output: s3a://lake-06/silver/prices/dt=<ds>/  (parquet)
"""

from __future__ import annotations

from datetime import datetime

from airflow.sdk import dag, task

RAW_DIR = "/opt/sandbox/data/raw"
SILVER_ROOT = "s3a://lake-06/silver/prices"


@task
def build_silver_partition(dt: str):
    """Run the day's silver build as an embedded local-mode Spark job.

    Requirements:
    - Read RAW_DIR/dt=<dt>/prices.ndjson with spark.read.json in a mode that
      TOLERATES corrupt lines instead of failing the whole job or silently
      nulling them beyond recognition. You need to be able to tell exactly
      which rows came from unparseable lines. (Spark's JSON reader has a
      documented mechanism for this — find it. There is also a documented
      catch: filtering on that mechanism's output column straight after
      reading doesn't behave the way you'd expect until you materialize the
      parsed data.)
    - Drop the rows that came from corrupt lines, and drop exact duplicate
      rows (the raw dumps contain byte-identical repeated lines; identical
      lines parse to identical rows).
    - The corrupt-line bookkeeping column must NOT survive into the output.
    - Write parquet to SILVER_ROOT/dt=<dt>/ with overwrite semantics for
      exactly that partition: rerunning the task for a day replaces that
      day's files and leaves the row count unchanged — never appends, never
      touches other days.
    - Missing input for dt -> raise (fail), as in task 04.

    Build the SparkSession exactly like dags/smoke_env.py does (endpoint
    http://minio:9000, creds sandbox/sandbox123, path-style access) and stop
    it in a finally block — a leaked JVM in the scheduler container will
    bite the next run.

    TODO: implement.
    """
    raise NotImplementedError


@dag(
    dag_id="t07_spark_lake",
    schedule=None,
    start_date=datetime(2025, 1, 1),
    catchup=False,
    tags=["spark", "silver-lake"],
)
def t07_spark_lake():
    # TODO: wire build_silver_partition with the run's logical date.
    raise NotImplementedError


t07_spark_lake()
