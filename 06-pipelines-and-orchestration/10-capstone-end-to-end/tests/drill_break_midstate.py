"""GIVEN drill tool for CP2 — do not edit, do not read this for "the answer."

Simulates a half-dead pipeline: deletes mart.daily_category_prices rows and
the corresponding silver-lake parquet partitions for 3 fixed days, while
leaving core.price_records (and every other day) untouched. Your job is to
recover exactly those 3 days — rebuild their mart rows and silver
partitions — via a scoped re-run, without reprocessing (and therefore
without duplicating) core for any day, healthy or not.

This script creates ONLY an input state and a pre-drill snapshot manifest.
It contains no recovery logic. `validate_cp2.py` reads the manifest this
script writes and checks that your recovery touched only the 3 affected
days.

Run this AFTER CP1 passes (i.e. after a full, successful 14-day backfill) —
it snapshots current state before breaking anything, so running it against
an already-broken or partially-loaded pipeline produces a meaningless
snapshot.

Usage (from this task's directory):

    uv run python tests/drill_break_midstate.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))

from harness.common import load_ground_truth, not_passed, pg_connect  # noqa: E402

AFFECTED_DAYS = ["2025-06-03", "2025-06-07", "2025-06-11"]
MANIFEST_PATH = TASK_ROOT / "tests" / "midstate-manifest-local.json"

LAKE_BUCKET = "lake-06"
SILVER_PREFIX = "silver/prices"
MINIO_ENDPOINT_CANDIDATES = ["http://localhost:9601", "http://127.0.0.1:9601"]
MINIO_ACCESS_KEY = "sandbox"
MINIO_SECRET_KEY = "sandbox123"


def _s3_client():
    import boto3
    from botocore.config import Config

    last_err = None
    for endpoint in MINIO_ENDPOINT_CANDIDATES:
        try:
            client = boto3.client(
                "s3",
                endpoint_url=endpoint,
                aws_access_key_id=MINIO_ACCESS_KEY,
                aws_secret_access_key=MINIO_SECRET_KEY,
                config=Config(signature_version="s3v4"),
            )
            client.list_buckets()
            return client
        except Exception as e:  # noqa: BLE001
            last_err = e
    not_passed(f"could not reach MinIO at any of {MINIO_ENDPOINT_CANDIDATES}: {last_err}")


def _delete_silver_partition(s3, dt: str) -> int:
    prefix = f"{SILVER_PREFIX}/dt={dt}/"
    paginator = s3.get_paginator("list_objects_v2")
    keys = []
    for page in paginator.paginate(Bucket=LAKE_BUCKET, Prefix=prefix):
        for obj in page.get("Contents", []):
            keys.append({"Key": obj["Key"]})
    if keys:
        s3.delete_objects(Bucket=LAKE_BUCKET, Delete={"Objects": keys})
    return len(keys)


def main():
    gt = load_ground_truth()
    days = gt["days"]
    conn = pg_connect()
    s3 = _s3_client()

    snapshot_core_count = {}
    snapshot_core_loaded_at = {}
    snapshot_mart_count = {}

    with conn.cursor() as cur:
        for dt in days:
            cur.execute("SELECT count(*), max(loaded_at) FROM core.price_records WHERE dt = %s", (dt,))
            count, loaded_at = cur.fetchone()
            snapshot_core_count[dt] = count
            snapshot_core_loaded_at[dt] = loaded_at.isoformat() if loaded_at else None

            cur.execute("SELECT count(*) FROM mart.daily_category_prices WHERE dt = %s", (dt,))
            snapshot_mart_count[dt] = cur.fetchone()[0]

        if any(snapshot_core_count[dt] == 0 for dt in AFFECTED_DAYS):
            not_passed(
                "one or more affected days have zero core rows — run the CP1 full backfill "
                "successfully before running this drill"
            )

        generated_at = datetime.now(timezone.utc).isoformat()

        for dt in AFFECTED_DAYS:
            cur.execute("DELETE FROM mart.daily_category_prices WHERE dt = %s", (dt,))

    conn.commit()

    deleted_objects = {}
    for dt in AFFECTED_DAYS:
        deleted_objects[dt] = _delete_silver_partition(s3, dt)

    conn.close()

    manifest = {
        "affected_days": AFFECTED_DAYS,
        "generated_at": generated_at,
        "pre_drill_core_counts": snapshot_core_count,
        "pre_drill_core_loaded_at": snapshot_core_loaded_at,
        "pre_drill_mart_counts": snapshot_mart_count,
        "deleted_silver_objects": deleted_objects,
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print(f"deleted mart rows and silver partitions for: {AFFECTED_DAYS}")
    print(f"wrote manifest {MANIFEST_PATH}")


if __name__ == "__main__":
    main()
