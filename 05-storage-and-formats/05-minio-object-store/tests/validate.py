"""Validator for 05-minio-object-store.

Run from the module root:
    uv run python 05-minio-object-store/tests/validate.py
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import boto3
import pyarrow.dataset as ds
import pyarrow.fs as pafs

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))

from harness.common import (  # noqa: E402
    DATA_DIR,
    S3_ACCESS_KEY,
    S3_BUCKET,
    S3_SECRET_KEY,
    approx,
    check_notes_filled,
    fail,
    guarded,
    load_ground_truth,
    load_results,
    minio_endpoint,
    passed,
)

LAKE_DIR = DATA_DIR / "lake"
TRAP_DIR = DATA_DIR / "lake-trap"
RESULTS_PATH = TASK_ROOT / "results-local.json"

FILE_COUNT_RATIO = 20


def s3_client():
    return boto3.client(
        "s3",
        endpoint_url=minio_endpoint(),
        aws_access_key_id=S3_ACCESS_KEY,
        aws_secret_access_key=S3_SECRET_KEY,
        region_name="us-east-1",
    )


def common_prefixes(client, bucket, prefix):
    paginator = client.get_paginator("list_objects_v2")
    prefixes = set()
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix, Delimiter="/"):
        for cp in page.get("CommonPrefixes", []):
            prefixes.add(cp["Prefix"])
    return prefixes


def object_count(client, bucket, prefix):
    paginator = client.get_paginator("list_objects_v2")
    count = 0
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        count += len(page.get("Contents", []))
    return count


def covered_months(date_from, date_to):
    d0 = datetime.strptime(date_from, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    d1 = datetime.strptime(date_to, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    months = []
    cur = d0.replace(day=1)
    while cur <= d1:
        key = f"{cur.year:04d}-{cur.month:02d}"
        if key not in months:
            months.append(key)
        cur = cur.replace(year=cur.year + 1, month=1) if cur.month == 12 else cur.replace(month=cur.month + 1)
    return months


@guarded
def main():
    gt = load_ground_truth()

    if not LAKE_DIR.exists() or not TRAP_DIR.exists():
        fail(f"expected {LAKE_DIR} and {TRAP_DIR} to exist locally (task 04 outputs)")

    client = s3_client()

    # --- lake/ prefix has exactly the 18 month= sub-prefixes, no extras ---
    expected_dirs = {f"lake/month={k}/" for k in gt["rows_by_month"]}
    actual_dirs = common_prefixes(client, S3_BUCKET, "lake/")
    missing = expected_dirs - actual_dirs
    extra = actual_dirs - expected_dirs
    if missing:
        fail(f"bucket lake/ missing month prefixes: {sorted(missing)} — run tests/bench.py first")
    if extra:
        fail(f"bucket lake/ has unexpected extra prefixes: {sorted(extra)}")

    # --- object count under lake/ matches local file count ---
    local_lake_files = sum(1 for _ in LAKE_DIR.rglob("*.parquet"))
    lake_object_count = object_count(client, S3_BUCKET, "lake/")
    if lake_object_count != local_lake_files:
        fail(f"bucket lake/ has {lake_object_count} objects, local data/lake has {local_lake_files} parquet files")

    # --- s3 lake dataset: row count and probe query ---
    host = minio_endpoint().split("://", 1)[1]
    fs = pafs.S3FileSystem(
        endpoint_override=host,
        scheme="http",
        access_key=S3_ACCESS_KEY,
        secret_key=S3_SECRET_KEY,
    )
    s3_lake_dataset = ds.dataset(f"{S3_BUCKET}/lake", filesystem=fs, partitioning="hive", format="parquet")

    total_rows = s3_lake_dataset.count_rows()
    if total_rows != gt["total_rows"]:
        fail(f"s3 lake dataset total rows: expected {gt['total_rows']}, got {total_rows}")

    fp = gt["filter_probe"]
    months = covered_months(fp["captured_at_from"], fp["captured_at_to"])
    ts_from = datetime.strptime(fp["captured_at_from"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    ts_to = datetime.strptime(fp["captured_at_to"], "%Y-%m-%d").replace(tzinfo=timezone.utc) + timedelta(days=1)
    full_filter = (
        ds.field("month").isin(months)
        & (ds.field("source_id") == fp["source_id"])
        & (ds.field("captured_at") >= ts_from)
        & (ds.field("captured_at") < ts_to)
    )
    probe_table = s3_lake_dataset.to_table(filter=full_filter, columns=["price"])
    if probe_table.num_rows != fp["rows"]:
        fail(f"s3 lake filter_probe rows: expected {fp['rows']}, got {probe_table.num_rows}")
    probe_sum = sum(v for v in probe_table.column("price").to_pylist() if v is not None)
    approx(probe_sum, fp["price_sum"], rel_tol=1e-6, what="s3 lake filter_probe price_sum")

    # --- lake-trap/ object count is a structural small-files signal ---
    trap_object_count = object_count(client, S3_BUCKET, "lake-trap/")
    if trap_object_count == 0:
        fail("bucket has no objects under lake-trap/ — run tests/bench.py first")
    if trap_object_count < FILE_COUNT_RATIO * lake_object_count:
        fail(
            f"bucket lake-trap/ has {trap_object_count} objects, lake/ has {lake_object_count} — "
            f"expected trap to have >= {FILE_COUNT_RATIO}x ({FILE_COUNT_RATIO * lake_object_count})"
        )

    # --- results-local.json from bench.py ---
    results = load_results(RESULTS_PATH, what="results-local.json")
    for name in ("lake", "lake-trap"):
        if name not in results.get("prefixes", {}):
            fail(f"results-local.json missing prefixes['{name}'] — rerun tests/bench.py")
        for key in ("object_count", "list_pages", "list_wall_s"):
            if key not in results["prefixes"][name]:
                fail(f"results-local.json prefixes['{name}'] missing '{key}' — rerun tests/bench.py")

    lake_pages = results["prefixes"]["lake"]["list_pages"]
    trap_pages = results["prefixes"]["lake-trap"]["list_pages"]
    if trap_pages <= lake_pages:
        fail(
            f"results-local.json: expected lake-trap/ ({trap_pages} LIST pages) to need more pages "
            f"than lake/ ({lake_pages}) — did bench.py run after both prefixes were fully uploaded?"
        )

    check_notes_filled(TASK_ROOT / "NOTES.md")

    passed(
        f"lake/: {lake_object_count} objects across {len(actual_dirs)} months; "
        f"lake-trap/: {trap_object_count} objects ({trap_object_count / max(lake_object_count, 1):.1f}x); "
        f"probe rows={probe_table.num_rows}"
    )


if __name__ == "__main__":
    main()
