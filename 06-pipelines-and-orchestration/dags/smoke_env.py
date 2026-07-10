"""Environment smoke test, not a learner task.

Exercises every stack component wired up by docker-compose.yml: warehouse Postgres
via psycopg, alert-sink over HTTP, and a local pyspark session with an s3a
round trip against MinIO. Run with:

    docker compose exec airflow-scheduler airflow dags test smoke_env 2025-06-01
"""

from __future__ import annotations

import json
import urllib.request
from datetime import datetime

from airflow.sdk import dag, task


@task
def check_warehouse():
    import psycopg

    with psycopg.connect("postgresql://sandbox:sandbox@warehouse:5432/pipelines") as conn:
        with conn.cursor() as cur:
            cur.execute("CREATE TABLE IF NOT EXISTS ops.smoke_env (id int, note text)")
            cur.execute("INSERT INTO ops.smoke_env (id, note) VALUES (1, 'smoke_env ok')")
            cur.execute("SELECT note FROM ops.smoke_env WHERE id = 1")
            row = cur.fetchone()
        conn.commit()
    assert row is not None and row[0] == "smoke_env ok"


@task
def check_alert_sink():
    body = json.dumps({"source": "smoke_env", "level": "info"}).encode()
    req = urllib.request.Request(
        "http://alert-sink:8000/alert", data=body, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200


@task
def check_spark():
    from pyspark.sql import SparkSession

    spark = (
        SparkSession.builder.appName("smoke_env")
        .config("spark.hadoop.fs.s3a.endpoint", "http://minio:9000")
        .config("spark.hadoop.fs.s3a.access.key", "sandbox")
        .config("spark.hadoop.fs.s3a.secret.key", "sandbox123")
        .config("spark.hadoop.fs.s3a.path.style.access", "true")
        .config("spark.hadoop.fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem")
        .master("local[2]")
        .getOrCreate()
    )
    try:
        assert spark.range(10).count() == 10

        path = "s3a://lake-06/smoke_env/roundtrip"
        spark.range(5).write.mode("overwrite").parquet(path)
        assert spark.read.parquet(path).count() == 5
    finally:
        spark.stop()


@dag(
    dag_id="smoke_env",
    schedule=None,
    start_date=datetime(2025, 1, 1),
    catchup=False,
    tags=["smoke-test", "infra"],
)
def smoke_env():
    check_warehouse()
    check_alert_sink()
    check_spark()


smoke_env()
