"""Validator for 06-delta-lake.

Run from the module root:
    uv run python 06-delta-lake/tests/validate.py
"""

import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))

from harness.common import (  # noqa: E402
    S3_ACCESS_KEY,
    S3_BUCKET,
    S3_SECRET_KEY,
    approx,
    check_notes_filled,
    fail,
    guarded,
    load_ground_truth,
    minio_endpoint,
    passed,
)

TABLE_URI = str(MODULE_ROOT / "data" / "delta" / "snapshots")
S3_TABLE_URI = f"s3://{S3_BUCKET}/delta/snapshots"
STORAGE_OPTIONS = {
    "AWS_ENDPOINT_URL": minio_endpoint(),
    "AWS_ACCESS_KEY_ID": S3_ACCESS_KEY,
    "AWS_SECRET_ACCESS_KEY": S3_SECRET_KEY,
    "AWS_ALLOW_HTTP": "true",
    "AWS_S3_ALLOW_UNSAFE_RENAME": "true",
}

# structural bounds, not exact magic numbers
MIN_APPEND_COMMITS = 2
COMPACT_REMOVE_TO_ADD_RATIO = 2
MAX_FILES_AFTER_COMPACT = 3


def _import_deltalake():
    try:
        from deltalake import DeltaTable
    except ImportError:
        fail("deltalake package not importable — check `uv sync` ran for this module")
    return DeltaTable


@guarded
def main():
    DeltaTable = _import_deltalake()
    gt = load_ground_truth()
    total_rows = gt["total_rows"]
    rows_by_month = gt["rows_by_month"]
    price_sum_by_month = gt["price_sum_by_month"]
    last_month = max(rows_by_month)  # "YYYY-MM" strings sort chronologically

    if not Path(TABLE_URI).exists():
        fail(f"{TABLE_URI} does not exist — run src/delta_pipeline.py first")

    dt = DeltaTable(TABLE_URI)

    # --- (1) latest version row count + per-month price sums ---
    latest_table = dt.to_pyarrow_dataset().to_table(columns=["month", "price"])
    if latest_table.num_rows != total_rows:
        fail(f"latest version row count: expected {total_rows}, got {latest_table.num_rows}")

    months_col = latest_table.column("month").to_pylist()
    price_col = latest_table.column("price").to_pylist()
    sums = {}
    for m, p in zip(months_col, price_col):
        if p is not None:
            sums[m] = sums.get(m, 0.0) + p
    for month, expected_sum in price_sum_by_month.items():
        approx(sums.get(month, 0.0), expected_sum, rel_tol=1e-6, what=f"price_sum_by_month[{month}]")

    # --- history-derived commit structure ---
    history = sorted(dt.history(), key=lambda h: h["version"])  # ascending
    if not history or history[0].get("operation") != "WRITE":
        fail("version 0 is not a WRITE commit — unexpected table history shape")

    append_versions = [
        h["version"] for h in history
        if h.get("operation") == "WRITE" and h.get("operationParameters", {}).get("mode") == "Append"
    ]
    if len(append_versions) < MIN_APPEND_COMMITS:
        fail(
            f"expected >= {MIN_APPEND_COMMITS} append-mode commits after the initial write, "
            f"found {len(append_versions)} — append_last_month must split the last month into "
            "multiple separate mode='append' writes, not one"
        )

    first_append_version = min(append_versions)
    pre_append_version = first_append_version - 1
    if pre_append_version < 0:
        fail(f"first append commit is version {first_append_version}, expected it after an initial write")

    # --- (2) time travel: row count and partition absence before the first append ---
    dt_pre = DeltaTable(TABLE_URI, version=pre_append_version)
    pre_rows = dt_pre.to_pyarrow_dataset().count_rows()
    expected_pre_rows = total_rows - rows_by_month[last_month]
    if pre_rows != expected_pre_rows:
        fail(
            f"row count at version {pre_append_version} (before first append): "
            f"expected {expected_pre_rows}, got {pre_rows}"
        )
    pre_partitions = {p.get("month") for p in dt_pre.partitions()}
    if last_month in pre_partitions:
        fail(
            f"version {pre_append_version} already has partition month={last_month} — "
            "initial_load must not include the last month"
        )

    # --- (4) schema evolution ---
    latest_schema_names = dt.schema().to_arrow().names
    if "price_bucket" not in latest_schema_names:
        fail(f"latest schema missing 'price_bucket' — got {latest_schema_names}")
    dt_v0 = DeltaTable(TABLE_URI, version=0)
    v0_schema_names = dt_v0.schema().to_arrow().names
    if "price_bucket" in v0_schema_names:
        fail("version 0 schema already has 'price_bucket' — schema evolution must not rewrite old commits")

    # --- (5) compaction ---
    optimize_entries = [h for h in history if h.get("operation") == "OPTIMIZE"]
    if not optimize_entries:
        fail("no OPTIMIZE operation found in table history — run compact()")
    opt = optimize_entries[-1]
    metrics = opt.get("operationMetrics") or {}
    added = int(metrics.get("numFilesAdded", 0))
    removed = int(metrics.get("numFilesRemoved", 0))
    if added == 0 or removed == 0:
        fail(f"OPTIMIZE metrics look empty: numFilesAdded={added}, numFilesRemoved={removed}")
    if removed <= added:
        fail(f"OPTIMIZE should remove more files than it adds: added={added}, removed={removed}")
    if removed < COMPACT_REMOVE_TO_ADD_RATIO * added:
        fail(
            f"OPTIMIZE removed only {removed} files for {added} added — expected removed >= "
            f"{COMPACT_REMOVE_TO_ADD_RATIO}x added (weak compaction, or compact() ran on an "
            "already-small file set)"
        )

    last_month_dir = Path(TABLE_URI) / f"month={last_month}"
    live_files = list(last_month_dir.glob("*.parquet"))
    if len(live_files) > MAX_FILES_AFTER_COMPACT:
        fail(
            f"month={last_month} still has {len(live_files)} parquet files after compact+vacuum, "
            f"expected <= {MAX_FILES_AFTER_COMPACT} — did vacuum actually delete the old files?"
        )

    post_compact_rows = DeltaTable(TABLE_URI).to_pyarrow_dataset().count_rows()
    if post_compact_rows != total_rows:
        fail(f"row count changed after compact+vacuum: expected {total_rows}, got {post_compact_rows}")

    # --- (6) MinIO leg ---
    try:
        dt_s3 = DeltaTable(S3_TABLE_URI, storage_options=STORAGE_OPTIONS)
    except Exception as e:
        fail(
            f"could not load Delta table at {S3_TABLE_URI}: {type(e).__name__}: {e} — "
            "run src/delta_pipeline.py's MinIO leg with MinIO up (`docker compose up -d --wait`)"
        )
    if dt_s3.version() < 1:
        fail(f"{S3_TABLE_URI} has version {dt_s3.version()} — expected at least one commit past the initial write")
    s3_rows = dt_s3.to_pyarrow_dataset().count_rows()
    if s3_rows != total_rows:
        fail(f"{S3_TABLE_URI} row count: expected {total_rows}, got {s3_rows}")

    # --- (7) NOTES.md ---
    check_notes_filled(TASK_ROOT / "NOTES.md")

    passed(
        f"local table v{dt.version()}: {total_rows} rows, {len(append_versions)} append commits, "
        f"OPTIMIZE removed {removed}/{added + removed} files, month={last_month} down to "
        f"{len(live_files)} files; s3 table v{dt_s3.version()}: {s3_rows} rows"
    )


if __name__ == "__main__":
    main()
