"""CP1 validator for 10-capstone-end-to-end: build + full 14-day backfill.

Checks, for every day in data/ground-truth.json's "days" list:

  1. core.price_records row count for that dt equals ground truth's
     valid_records for that dt (exact).
  2. Per-currency count and price_sum for that dt (computed from
     core.price_records, grouped by currency) match ground truth's
     per_day_currency[dt] — count exact, price_sum within 0.02 absolute.
  3. mart.daily_category_prices is internally consistent with core: this
     validator independently recomputes (n_records, avg_price, max_price)
     per (dt, category, currency) directly from core.price_records via SQL
     and compares against the mart table's stored rows — same group keys,
     n_records exact, avg_price/max_price within 0.02.
  4. A silver-lake parquet partition exists at
     s3a://lake-06/silver/prices/dt=<dt>/ with a row count equal to that
     day's core.price_records row count. This is the identity this module
     picked for "plausible counts": the Spark stage in this capstone's
     topology reads from core (already deduped and contract-validated), so
     the lake for day X should hold exactly core's row count for day X, not
     GT's parseable_records (which still includes invalid/duplicate lines
     the earlier pipeline stages already dropped). See
     .authoring/notes-tasks-10-bonus.md for the full reasoning.
  5. ops.load_audit has at least one row for that dt whose status does not
     look like a failure (case-insensitive, does not contain "fail" or
     "error"). This validator does not assume an exact status vocabulary
     from tasks 01-07 — only that a failure is spelled recognizably.

Run from this task's directory:

    uv run python tests/validate_cp1.py
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))

from harness.common import (  # noqa: E402
    guarded,
    load_ground_truth,
    not_passed,
    passed,
    pg_connect,
)

PRICE_SUM_TOL = 0.02
MART_NUM_TOL = 0.02

MINIO_ENDPOINT_CANDIDATES = [
    "http://localhost:9601",
    "http://127.0.0.1:9601",
]
MINIO_ACCESS_KEY = "sandbox"
MINIO_SECRET_KEY = "sandbox123"
LAKE_BUCKET = "lake-06"
SILVER_PREFIX = "silver/prices"


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


def _silver_partition_row_count(s3, dt: str) -> int:
    import pyarrow.parquet as pq

    prefix = f"{SILVER_PREFIX}/dt={dt}/"
    paginator = s3.get_paginator("list_objects_v2")
    total = 0
    found_any = False
    for page in paginator.paginate(Bucket=LAKE_BUCKET, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if not key.endswith(".parquet"):
                continue
            found_any = True
            body = s3.get_object(Bucket=LAKE_BUCKET, Key=key)["Body"].read()
            pf = pq.ParquetFile(io.BytesIO(body))
            total += pf.metadata.num_rows
    if not found_any:
        return -1
    return total


def verify_days(gt, conn, s3, days):
    """Run all CP1 structural checks (core counts, per-currency sums, mart
    consistency, silver-lake partitions, audit rows) for the given list of
    dt strings. Returns a list of failure strings (empty if everything
    checked out). Reused by validate_cp2.py to re-check the original 14
    days after a scoped recovery.
    """
    per_day = gt["per_day"]
    per_day_currency = gt["per_day_currency"]

    failures = []

    with conn.cursor() as cur:
        for dt in days:
            expected_valid = per_day[dt]["valid_records"]

            cur.execute("SELECT count(*) FROM core.price_records WHERE dt = %s", (dt,))
            core_count = cur.fetchone()[0]
            if core_count != expected_valid:
                failures.append(
                    f"{dt}: core.price_records count {core_count} != ground truth valid_records {expected_valid}"
                )
                continue

            cur.execute(
                "SELECT currency, count(*), sum(price) FROM core.price_records "
                "WHERE dt = %s GROUP BY currency",
                (dt,),
            )
            rows = {r[0]: (r[1], float(r[2])) for r in cur.fetchall()}
            for currency, expected in per_day_currency[dt].items():
                if currency not in rows:
                    failures.append(f"{dt}/{currency}: no rows in core.price_records")
                    continue
                got_count, got_sum = rows[currency]
                if got_count != expected["count"]:
                    failures.append(
                        f"{dt}/{currency}: count {got_count} != expected {expected['count']}"
                    )
                if abs(got_sum - expected["price_sum"]) > PRICE_SUM_TOL:
                    failures.append(
                        f"{dt}/{currency}: price_sum {got_sum} != expected {expected['price_sum']} "
                        f"(tolerance {PRICE_SUM_TOL})"
                    )

            cur.execute(
                "SELECT category, currency, count(*), avg(price), max(price) "
                "FROM core.price_records WHERE dt = %s GROUP BY category, currency",
                (dt,),
            )
            recomputed = {
                (r[0], r[1]): {"n_records": r[2], "avg_price": float(r[3]), "max_price": float(r[4])}
                for r in cur.fetchall()
            }

            cur.execute(
                "SELECT category, currency, n_records, avg_price, max_price "
                "FROM mart.daily_category_prices WHERE dt = %s",
                (dt,),
            )
            mart_rows = {
                (r[0], r[1]): {"n_records": r[2], "avg_price": float(r[3]), "max_price": float(r[4])}
                for r in cur.fetchall()
            }

            if set(recomputed.keys()) != set(mart_rows.keys()):
                missing = set(recomputed.keys()) - set(mart_rows.keys())
                extra = set(mart_rows.keys()) - set(recomputed.keys())
                failures.append(
                    f"{dt}: mart group keys mismatch vs core recompute "
                    f"(missing={sorted(missing)}, extra={sorted(extra)})"
                )
            else:
                for key, expected in recomputed.items():
                    got = mart_rows[key]
                    if got["n_records"] != expected["n_records"]:
                        failures.append(
                            f"{dt}/{key}: mart n_records {got['n_records']} != recomputed {expected['n_records']}"
                        )
                    if abs(got["avg_price"] - expected["avg_price"]) > MART_NUM_TOL:
                        failures.append(
                            f"{dt}/{key}: mart avg_price {got['avg_price']} != recomputed "
                            f"{expected['avg_price']} (tolerance {MART_NUM_TOL})"
                        )
                    if abs(got["max_price"] - expected["max_price"]) > MART_NUM_TOL:
                        failures.append(
                            f"{dt}/{key}: mart max_price {got['max_price']} != recomputed "
                            f"{expected['max_price']} (tolerance {MART_NUM_TOL})"
                        )

            silver_count = _silver_partition_row_count(s3, dt)
            if silver_count == -1:
                failures.append(f"{dt}: no silver-lake parquet partition found at "
                                 f"s3a://{LAKE_BUCKET}/{SILVER_PREFIX}/dt={dt}/")
            elif silver_count != core_count:
                failures.append(
                    f"{dt}: silver-lake row count {silver_count} != core.price_records count {core_count}"
                )

            cur.execute(
                "SELECT status FROM ops.load_audit WHERE dt = %s",
                (dt,),
            )
            audit_rows = cur.fetchall()
            if not audit_rows:
                failures.append(f"{dt}: no ops.load_audit rows found")
            else:
                statuses = [str(r[0]).lower() for r in audit_rows]
                if all(("fail" in s or "error" in s) for s in statuses):
                    failures.append(f"{dt}: all ops.load_audit rows look like failures: {statuses}")

    return failures


@guarded
def main():
    gt = load_ground_truth()
    days = gt["days"]

    conn = pg_connect()
    s3 = _s3_client()

    failures = verify_days(gt, conn, s3, days)

    conn.close()

    if failures:
        not_passed("; ".join(failures[:8]) + (f" (+{len(failures) - 8} more)" if len(failures) > 8 else ""))

    passed(f"all {len(days)} days verified: core counts, per-currency sums, mart consistency, "
           f"silver-lake partitions, audit rows")


if __name__ == "__main__":
    main()
