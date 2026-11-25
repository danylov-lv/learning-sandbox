"""Benchmark harness for 05-minio-object-store.

Uploads data/lake -> prefix "lake/" and data/lake-trap -> prefix "lake-trap/"
via the learner's upload(), using their concurrent upload code (skips
re-upload if the bucket already holds the right number of objects under a
prefix). Then measures LIST enumeration cost for each prefix, a probe query
against the S3 lake vs the same probe against local disk, and a single-month
aggregate against the S3 lake vs the S3 trap. Writes results-local.json next
to this file.

Run from the module root:
    uv run python 05-minio-object-store/tests/bench.py
"""

import json
import sys
import time
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
    fail,
    guarded,
    load_ground_truth,
    load_learner_module,
    minio_endpoint,
)

LAKE_DIR = DATA_DIR / "lake"
TRAP_DIR = DATA_DIR / "lake-trap"
RESULTS_PATH = TASK_ROOT / "results-local.json"

PREFIXES = [("lake", LAKE_DIR), ("lake-trap", TRAP_DIR)]


def s3_client():
    return boto3.client(
        "s3",
        endpoint_url=minio_endpoint(),
        aws_access_key_id=S3_ACCESS_KEY,
        aws_secret_access_key=S3_SECRET_KEY,
        region_name="us-east-1",
    )


def s3_filesystem():
    host = minio_endpoint().split("://", 1)[1]
    return pafs.S3FileSystem(
        endpoint_override=host,
        scheme="http",
        access_key=S3_ACCESS_KEY,
        secret_key=S3_SECRET_KEY,
    )


def local_file_count(base_dir):
    return sum(1 for _ in Path(base_dir).rglob("*.parquet"))


def list_prefix(client, bucket, prefix):
    """Paginate LIST for a prefix; return (object_count, page_count, wall_s)."""
    paginator = client.get_paginator("list_objects_v2")
    t0 = time.perf_counter()
    object_count = 0
    page_count = 0
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        page_count += 1
        object_count += len(page.get("Contents", []))
    wall = time.perf_counter() - t0
    return object_count, page_count, wall


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


def probe_filter(gt, month_field=None):
    fp = gt["filter_probe"]
    ts_from = datetime.strptime(fp["captured_at_from"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    ts_to = datetime.strptime(fp["captured_at_to"], "%Y-%m-%d").replace(tzinfo=timezone.utc) + timedelta(days=1)
    filt = (
        (ds.field("source_id") == fp["source_id"])
        & (ds.field("captured_at") >= ts_from)
        & (ds.field("captured_at") < ts_to)
    )
    if month_field is not None:
        months = covered_months(fp["captured_at_from"], fp["captured_at_to"])
        filt = ds.field(month_field).isin(months) & filt
    return filt


def run_probe(dataset, gt, month_field=None):
    filt = probe_filter(gt, month_field=month_field)
    t0 = time.perf_counter()
    table = dataset.to_table(filter=filt, columns=["price"])
    wall = time.perf_counter() - t0
    price_sum = float(sum(v for v in table.column("price").to_pylist() if v is not None))
    return {"wall_s": wall, "rows": table.num_rows, "price_sum": price_sum}


def run_month_agg(dataset, month_key, month_field=None):
    if month_field is not None:
        filt = ds.field(month_field) == month_key
    else:
        y, m = (int(x) for x in month_key.split("-"))
        start = datetime(y, m, 1, tzinfo=timezone.utc)
        end = datetime(y + 1, 1, 1, tzinfo=timezone.utc) if m == 12 else datetime(y, m + 1, 1, tzinfo=timezone.utc)
        filt = (ds.field("captured_at") >= start) & (ds.field("captured_at") < end)
    t0 = time.perf_counter()
    table = dataset.to_table(filter=filt, columns=["price"])
    wall = time.perf_counter() - t0
    return {"wall_s": wall, "rows": table.num_rows}


@guarded
def main():
    if not LAKE_DIR.exists() or not TRAP_DIR.exists():
        fail(f"expected {LAKE_DIR} and {TRAP_DIR} to exist — task 04's outputs, treated read-only here")

    gt = load_ground_truth()
    mod = load_learner_module(TASK_ROOT / "src" / "upload_lake.py", "upload_lake")
    if not hasattr(mod, "upload"):
        fail("src/upload_lake.py has no upload(local_dir, bucket, prefix) function")

    client = s3_client()

    for name, local_dir in PREFIXES:
        prefix = f"{name}/"
        expected_count = local_file_count(local_dir)
        existing_count, _, _ = list_prefix(client, S3_BUCKET, prefix)
        if existing_count == expected_count:
            print(f"skipping upload of {name}: bucket already has {existing_count} objects under '{prefix}'")
            continue
        print(f"uploading {local_dir} -> s3://{S3_BUCKET}/{prefix} ({expected_count} files) ...")
        t0 = time.perf_counter()
        uploaded = mod.upload(local_dir, S3_BUCKET, prefix)
        elapsed = time.perf_counter() - t0
        print(f"  uploaded {uploaded} objects in {elapsed:.1f}s")

    results = {"prefixes": {}}

    print()
    print(f"{'prefix':<12}{'objects':>10}{'list_pages':>12}{'list_wall_s':>14}")
    for name, local_dir in PREFIXES:
        prefix = f"{name}/"
        object_count, page_count, list_wall_s = list_prefix(client, S3_BUCKET, prefix)
        results["prefixes"][name] = {
            "object_count": object_count,
            "list_pages": page_count,
            "list_wall_s": list_wall_s,
        }
        print(f"{name:<12}{object_count:>10}{page_count:>12}{list_wall_s:>14.4f}")

    fs = s3_filesystem()
    s3_lake_dataset = ds.dataset(f"{S3_BUCKET}/lake", filesystem=fs, partitioning="hive", format="parquet")
    s3_trap_dataset = ds.dataset(f"{S3_BUCKET}/lake-trap", filesystem=fs, partitioning="hive", format="parquet")
    local_lake_dataset = ds.dataset(LAKE_DIR, partitioning="hive", format="parquet")

    print()
    print("running probe query (source + date range, month-pruned) ...")
    s3_probe = run_probe(s3_lake_dataset, gt, month_field="month")
    local_probe = run_probe(local_lake_dataset, gt, month_field="month")
    results["probe_query"] = {"s3_lake": s3_probe, "local_lake": local_probe}
    print(f"  s3 lake:    {s3_probe['wall_s']:.4f}s, {s3_probe['rows']} rows")
    print(f"  local lake: {local_probe['wall_s']:.4f}s, {local_probe['rows']} rows")

    month_key = max(gt["rows_by_month"], key=lambda k: gt["rows_by_month"][k])
    print(f"\nrunning single-month aggregate for month={month_key} ...")
    s3_lake_agg = run_month_agg(s3_lake_dataset, month_key, month_field="month")
    s3_trap_agg = run_month_agg(s3_trap_dataset, month_key, month_field=None)
    results["month_agg"] = {
        "month_key_used": month_key,
        "s3_lake": s3_lake_agg,
        "s3_lake_trap": s3_trap_agg,
    }
    print(f"  s3 lake:      {s3_lake_agg['wall_s']:.4f}s, {s3_lake_agg['rows']} rows")
    print(f"  s3 lake-trap: {s3_trap_agg['wall_s']:.4f}s, {s3_trap_agg['rows']} rows")

    RESULTS_PATH.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nwrote {RESULTS_PATH}")


if __name__ == "__main__":
    main()
