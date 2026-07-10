"""Validator for 07-spark-stage-silver-lake.

Run from the task directory:

    uv run python tests/validate.py

Expects the compose stack up, the DAG copied to dags/ and run for
2025-06-01, 2025-06-10, and 2025-06-14, and the operator-comparison section
in NOTES.md written. The validator reads MinIO directly from the host and
reruns one day itself to prove overwrite idempotency.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from harness import common  # noqa: E402
from harness.common import guarded, not_passed, passed  # noqa: E402

TASK_DIR = Path(__file__).resolve().parents[1]
DAG_ID = "t07_spark_lake"
DAYS = ["2025-06-01", "2025-06-10", "2025-06-14"]
RERUN_DAY = "2025-06-01"
BUCKET = "lake-06"
SILVER_PREFIX = "silver/prices"

NOTES_HEADING = "## Operator comparison"
NOTES_REQUIRED_TERMS = ["SparkSubmitOperator", "DockerOperator", "KubernetesPodOperator", "local"]
NOTES_MIN_PARAGRAPHS = 3
NOTES_MIN_PARAGRAPH_CHARS = 300


def minio_fs():
    from pyarrow import fs

    port = int(os.environ.get("SANDBOX_06_MINIO_PORT", "9601"))
    return fs.S3FileSystem(
        access_key="sandbox",
        secret_key="sandbox123",
        endpoint_override=f"http://localhost:{port}",
        scheme="http",
        connect_timeout=5,
        request_timeout=30,
    ), port


def partition_files(s3, day, port):
    from pyarrow import fs as pafs

    prefix = f"{BUCKET}/{SILVER_PREFIX}/dt={day}"
    try:
        infos = s3.get_file_info(pafs.FileSelector(prefix, recursive=True))
    except OSError as e:
        not_passed(f"cannot reach MinIO on localhost:{port} — is the compose stack up? ({e})")
    parquet = [i.path for i in infos if i.type == pafs.FileType.File and i.path.endswith(".parquet")]
    if not parquet:
        not_passed(f"no parquet files under s3://{prefix}/ — run the DAG for {day}")
    return parquet


def partition_count_and_schema(s3, day, port):
    import pyarrow.dataset as pads

    files = partition_files(s3, day, port)
    dataset = pads.dataset(files, format="parquet", filesystem=s3)
    return dataset.count_rows(), dataset.schema, len(files)


def expected_rows(gt, day):
    pd = gt["per_day"][day]
    return pd["parseable_records"] - pd["duplicate_lines"]


def rerun_dag(day):
    cmd = [
        "docker", "compose", "exec", "-T", "airflow-scheduler",
        "airflow", "dags", "test", DAG_ID, day,
    ]
    try:
        proc = subprocess.run(
            cmd, cwd=common.MODULE_ROOT, capture_output=True, text=True, timeout=900,
        )
    except FileNotFoundError:
        not_passed("docker not found on PATH — cannot rerun the DAG for the idempotency check")
    except subprocess.TimeoutExpired:
        not_passed(f"`airflow dags test {DAG_ID} {day}` timed out after 900s")
    if proc.returncode != 0:
        tail = (proc.stdout + proc.stderr).strip().splitlines()[-5:]
        not_passed(
            f"validator rerun of `airflow dags test {DAG_ID} {day}` failed "
            f"(is the compose stack up and the DAG copied to dags/?): {' | '.join(tail)}"
        )


def check_notes():
    notes_path = TASK_DIR / "NOTES.md"
    if not notes_path.exists():
        not_passed("NOTES.md not found in the task directory")
    text = notes_path.read_text(encoding="utf-8")

    m = re.search(re.escape(NOTES_HEADING) + r"\n(.*?)(?=\n## |\Z)", text, flags=re.S)
    if not m:
        not_passed(f'NOTES.md is missing the "{NOTES_HEADING}" section')
    body = re.sub(r"<!--.*?-->", "", m.group(1), flags=re.S)

    for term in NOTES_REQUIRED_TERMS:
        if term not in body:
            not_passed(f'the "{NOTES_HEADING}" section must discuss "{term}" — not found')

    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", body)]
    substantive = [p for p in paragraphs if len(p) >= NOTES_MIN_PARAGRAPH_CHARS and not p.startswith("#")]
    if len(substantive) < NOTES_MIN_PARAGRAPHS:
        not_passed(
            f'the "{NOTES_HEADING}" section has {len(substantive)} substantive paragraph(s) '
            f"(>= {NOTES_MIN_PARAGRAPH_CHARS} chars each); at least {NOTES_MIN_PARAGRAPHS} are required"
        )


@guarded
def main():
    check_notes()

    gt = common.load_ground_truth()
    for day in DAYS:
        if day not in gt["per_day"]:
            not_passed(f"{day} missing from ground-truth.json — regenerate data")

    s3, port = minio_fs()

    counts = {}
    for day in DAYS:
        rows, schema, _ = partition_count_and_schema(s3, day, port)
        expected = expected_rows(gt, day)
        if rows != expected:
            not_passed(
                f"silver partition dt={day} has {rows} rows, expected {expected} "
                "(parseable lines minus exact duplicate lines)"
            )
        corrupt_cols = [n for n in schema.names if "corrupt" in n.lower()]
        if corrupt_cols:
            not_passed(
                f"silver partition dt={day} still carries corrupt-record bookkeeping column(s) "
                f"{corrupt_cols} — drop them before writing"
            )
        counts[day] = rows

    rerun_dag(RERUN_DAY)

    rows_after, _, _ = partition_count_and_schema(s3, RERUN_DAY, port)
    if rows_after != counts[RERUN_DAY]:
        not_passed(
            f"rerun of {RERUN_DAY} changed the partition row count "
            f"({counts[RERUN_DAY]} -> {rows_after}) — the overwrite is not idempotent"
        )

    passed(
        f"silver partitions match ground truth for {', '.join(DAYS)}, "
        "rerun overwrites cleanly, NOTES.md comparison present"
    )


if __name__ == "__main__":
    main()
