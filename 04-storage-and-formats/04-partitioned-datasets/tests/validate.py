"""Validator for 04-partitioned-datasets.

Prints PASSED or `NOT PASSED: <reason>` and exits 0/1. No tracebacks reach
the learner.
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pyarrow.dataset as ds
import pyarrow.parquet as pq

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))

from harness.common import (  # noqa: E402
    approx,
    check_notes_filled,
    fail,
    guarded,
    load_ground_truth,
    load_results,
    passed,
)

LAKE_DIR = MODULE_ROOT / "data" / "lake"
TRAP_DIR = MODULE_ROOT / "data" / "lake-trap"
RESULTS_PATH = TASK_ROOT / "results-local.json"

CATEGORY_MIN_DIRS = 200  # measured 300 on the reference dataset; margin for smaller runs
FILE_COUNT_RATIO = 20  # trap must have >= this many times the month layout's file count


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


def parquet_files(base_dir):
    return sorted(Path(base_dir).rglob("*.parquet"))


@guarded
def main():
    gt = load_ground_truth()

    if not LAKE_DIR.exists():
        fail(f"{LAKE_DIR} does not exist — run tests/bench.py first (or implement build_lake.build)")
    if not TRAP_DIR.exists():
        fail(f"{TRAP_DIR} does not exist — run tests/bench.py first (or implement build_trap.build)")

    # --- partition directories match rows_by_month exactly ---
    expected_dirs = {f"month={k}" for k in gt["rows_by_month"]}
    actual_dirs = {p.name for p in LAKE_DIR.iterdir() if p.is_dir() and p.name.startswith("month=")}
    missing = expected_dirs - actual_dirs
    extra = actual_dirs - expected_dirs
    if missing:
        fail(f"data/lake missing partitions: {sorted(missing)}")
    if extra:
        fail(f"data/lake has unexpected extra partitions: {sorted(extra)}")

    # --- per-partition row counts via Parquet metadata only (no full data read) ---
    total_rows = 0
    for key, expected_count in gt["rows_by_month"].items():
        part_dir = LAKE_DIR / f"month={key}"
        files = parquet_files(part_dir)
        if not files:
            fail(f"partition month={key} has no parquet files")
        count = sum(pq.ParquetFile(f).metadata.num_rows for f in files)
        if count != expected_count:
            fail(f"month={key}: expected {expected_count} rows, found {count}")
        total_rows += count

    if total_rows != gt["total_rows"]:
        fail(f"total rows: expected {gt['total_rows']}, found {total_rows}")

    # --- compression codec sanity: at least one file actually uses ZSTD ---
    sample_file = parquet_files(LAKE_DIR)[0]
    md = pq.ParquetFile(sample_file).metadata
    codec = md.row_group(0).column(0).compression
    if "ZSTD" not in str(codec).upper():
        fail(f"expected zstd compression, found {codec} on {sample_file}")

    # --- per-file sortedness by (source_id, captured_at) ---
    for f in parquet_files(LAKE_DIR):
        tbl = pq.read_table(f, columns=["source_id", "captured_at"])
        source_ids = tbl.column("source_id").to_pylist()
        captured_ats = tbl.column("captured_at").to_pylist()
        prev = None
        for sid, cap in zip(source_ids, captured_ats):
            key = (sid, cap)
            if prev is not None and key < prev:
                fail(f"{f} is not sorted by (source_id, captured_at)")
            prev = key

    # --- per-month price sums via dataset scan ---
    dataset = ds.dataset(LAKE_DIR, partitioning="hive")
    for key, expected_sum in gt["price_sum_by_month"].items():
        table = dataset.to_table(filter=ds.field("month") == key, columns=["price"])
        actual_sum = sum(v for v in table.column("price").to_pylist() if v is not None)
        approx(actual_sum, expected_sum, rel_tol=1e-6, what=f"price_sum_by_month[{key}]")

    # --- structural pruning check ---
    fp = gt["filter_probe"]
    covered = covered_months(fp["captured_at_from"], fp["captured_at_to"])
    total_fragments = len(list(dataset.get_fragments()))
    month_only_filter = ds.field("month").isin(covered)
    touched = list(dataset.get_fragments(filter=month_only_filter))
    touched_count = len(touched)

    expected_touched = sum(len(parquet_files(LAKE_DIR / f"month={k}")) for k in covered)
    if touched_count != expected_touched:
        fail(
            f"pruning check: expected {expected_touched} fragments touched for months {covered}, "
            f"got {touched_count}"
        )
    if touched_count >= total_fragments:
        fail(
            f"pruning check: touched {touched_count}/{total_fragments} fragments — "
            "filtering by month did not prune anything"
        )

    # --- probe query correctness ---
    ts_from = datetime.strptime(fp["captured_at_from"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    ts_to = datetime.strptime(fp["captured_at_to"], "%Y-%m-%d").replace(tzinfo=timezone.utc) + timedelta(days=1)
    full_filter = (
        month_only_filter
        & (ds.field("source_id") == fp["source_id"])
        & (ds.field("captured_at") >= ts_from)
        & (ds.field("captured_at") < ts_to)
    )
    probe_table = dataset.to_table(filter=full_filter, columns=["price"])
    if probe_table.num_rows != fp["rows"]:
        fail(f"filter_probe rows: expected {fp['rows']}, got {probe_table.num_rows}")
    probe_sum = sum(v for v in probe_table.column("price").to_pylist() if v is not None)
    approx(probe_sum, fp["price_sum"], rel_tol=1e-6, what="filter_probe price_sum")

    # --- trap layout: cardinality and file-count explosion ---
    trap_dirs = [p for p in TRAP_DIR.iterdir() if p.is_dir() and p.name.startswith("category=")]
    if len(trap_dirs) < CATEGORY_MIN_DIRS:
        fail(f"data/lake-trap has only {len(trap_dirs)} category partitions, expected >= {CATEGORY_MIN_DIRS}")

    lake_file_count = len(parquet_files(LAKE_DIR))
    trap_file_count = len(parquet_files(TRAP_DIR))
    if trap_file_count < FILE_COUNT_RATIO * lake_file_count:
        fail(
            f"data/lake-trap has {trap_file_count} files, data/lake has {lake_file_count} — "
            f"expected trap to have >= {FILE_COUNT_RATIO}x ({FILE_COUNT_RATIO * lake_file_count})"
        )

    # --- results file from bench.py ---
    results = load_results(RESULTS_PATH, what="results-local.json")
    for section in ("month_layout", "trap_layout"):
        if section not in results:
            fail(f"results-local.json missing '{section}' — rerun tests/bench.py")
        for k in ("total_files", "median_file_size_bytes", "probe", "month_agg"):
            if k not in results[section]:
                fail(f"results-local.json['{section}'] missing '{k}' — rerun tests/bench.py")

    # --- NOTES.md ---
    check_notes_filled(TASK_ROOT / "NOTES.md")

    passed(
        f"lake: {lake_file_count} files across {len(actual_dirs)} months; "
        f"trap: {trap_file_count} files across {len(trap_dirs)} categories "
        f"({trap_file_count / max(lake_file_count, 1):.1f}x)"
    )


if __name__ == "__main__":
    main()
