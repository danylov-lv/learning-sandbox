"""Benchmark harness for 04-partitioned-datasets.

Builds both layouts by calling the learner's build() functions, then
measures file counts, median file size, probe-query wall time and files
touched, and single-month-aggregate wall time, for both the month lake and
the category trap. Writes results-local.json next to this file.
"""

import json
import statistics
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pyarrow.dataset as ds

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))

from harness.common import RAW_DIR, fail, load_ground_truth, load_learner_module  # noqa: E402

LAKE_DIR = MODULE_ROOT / "data" / "lake"
TRAP_DIR = MODULE_ROOT / "data" / "lake-trap"
RESULTS_PATH = TASK_ROOT / "results-local.json"


def covered_months(date_from, date_to):
    d0 = datetime.strptime(date_from, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    d1 = datetime.strptime(date_to, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    months = []
    cur = d0.replace(day=1)
    while cur <= d1:
        key = f"{cur.year:04d}-{cur.month:02d}"
        if key not in months:
            months.append(key)
        if cur.month == 12:
            cur = cur.replace(year=cur.year + 1, month=1)
        else:
            cur = cur.replace(month=cur.month + 1)
    return months


def parquet_files(base_dir):
    return sorted(Path(base_dir).rglob("*.parquet"))


def file_stats(base_dir):
    files = parquet_files(base_dir)
    sizes = [f.stat().st_size for f in files]
    return {
        "total_files": len(files),
        "median_file_size_bytes": int(statistics.median(sizes)) if sizes else 0,
        "total_bytes": sum(sizes),
    }


def probe_bench(base_dir, partitioning, gt, month_field=None):
    fp = gt["filter_probe"]
    dataset = ds.dataset(base_dir, partitioning=partitioning)
    total_fragments = len(list(dataset.get_fragments()))

    ts_from = datetime.strptime(fp["captured_at_from"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    ts_to = datetime.strptime(fp["captured_at_to"], "%Y-%m-%d").replace(tzinfo=timezone.utc) + timedelta(days=1)

    if month_field is not None:
        months = covered_months(fp["captured_at_from"], fp["captured_at_to"])
        month_only_filter = ds.field(month_field).isin(months)
        touched_fragments = len(list(dataset.get_fragments(filter=month_only_filter)))
        full_filter = (
            month_only_filter
            & (ds.field("source_id") == fp["source_id"])
            & (ds.field("captured_at") >= ts_from)
            & (ds.field("captured_at") < ts_to)
        )
    else:
        touched_fragments = total_fragments
        full_filter = (
            (ds.field("source_id") == fp["source_id"])
            & (ds.field("captured_at") >= ts_from)
            & (ds.field("captured_at") < ts_to)
        )

    t0 = time.perf_counter()
    table = dataset.to_table(filter=full_filter, columns=["price"])
    wall = time.perf_counter() - t0

    return {
        "wall_s": wall,
        "rows": table.num_rows,
        "price_sum": float(sum(v for v in table.column("price").to_pylist() if v is not None)),
        "fragments_touched": touched_fragments,
        "fragments_total": total_fragments,
    }


def month_agg_bench(base_dir, partitioning, month_key, month_field=None):
    dataset = ds.dataset(base_dir, partitioning=partitioning)
    y, m = (int(x) for x in month_key.split("-"))
    start = datetime(y, m, 1, tzinfo=timezone.utc)
    end = datetime(y + 1, 1, 1, tzinfo=timezone.utc) if m == 12 else datetime(y, m + 1, 1, tzinfo=timezone.utc)

    if month_field is not None:
        filt = ds.field(month_field) == month_key
    else:
        filt = (ds.field("captured_at") >= start) & (ds.field("captured_at") < end)

    t0 = time.perf_counter()
    table = dataset.to_table(filter=filt, columns=["price"])
    wall = time.perf_counter() - t0
    price_sum = float(sum(v for v in table.column("price").to_pylist() if v is not None))
    return {"wall_s": wall, "rows": table.num_rows, "price_sum": price_sum}


def main():
    gt = load_ground_truth()

    build_lake = load_learner_module(TASK_ROOT / "src" / "build_lake.py", "build_lake")
    build_trap = load_learner_module(TASK_ROOT / "src" / "build_trap.py", "build_trap")

    print("building data/lake (month partitioned)...")
    t0 = time.perf_counter()
    lake_rows = build_lake.build(str(RAW_DIR), str(LAKE_DIR))
    print(f"  {lake_rows:,} rows in {time.perf_counter() - t0:.1f}s")

    print("building data/lake-trap (category partitioned)...")
    t0 = time.perf_counter()
    trap_rows = build_trap.build(str(RAW_DIR), str(TRAP_DIR))
    print(f"  {trap_rows:,} rows in {time.perf_counter() - t0:.1f}s")

    month_key = max(gt["rows_by_month"], key=lambda k: gt["rows_by_month"][k])

    print("benchmarking probe query and month aggregate...")
    lake_probe = probe_bench(LAKE_DIR, "hive", gt, month_field="month")
    trap_probe = probe_bench(TRAP_DIR, "hive", gt, month_field=None)
    lake_agg = month_agg_bench(LAKE_DIR, "hive", month_key, month_field="month")
    trap_agg = month_agg_bench(TRAP_DIR, "hive", month_key, month_field=None)

    results = {
        "month_key_used_for_agg": month_key,
        "month_layout": {
            **file_stats(LAKE_DIR),
            "rows_written": lake_rows,
            "probe": lake_probe,
            "month_agg": lake_agg,
        },
        "trap_layout": {
            **file_stats(TRAP_DIR),
            "rows_written": trap_rows,
            "probe": trap_probe,
            "month_agg": trap_agg,
        },
    }
    RESULTS_PATH.write_text(json.dumps(results, indent=2), encoding="utf-8")

    print()
    print(f"{'metric':<32} {'lake (month)':>16} {'lake-trap (category)':>22}")
    print(f"{'total files':<32} {results['month_layout']['total_files']:>16} {results['trap_layout']['total_files']:>22}")
    print(f"{'median file size (bytes)':<32} {results['month_layout']['median_file_size_bytes']:>16} {results['trap_layout']['median_file_size_bytes']:>22}")
    print(f"{'probe wall (s)':<32} {results['month_layout']['probe']['wall_s']:>16.4f} {results['trap_layout']['probe']['wall_s']:>22.4f}")
    print(f"{'probe fragments touched/total':<32} {str(results['month_layout']['probe']['fragments_touched']) + '/' + str(results['month_layout']['probe']['fragments_total']):>16} {str(results['trap_layout']['probe']['fragments_touched']) + '/' + str(results['trap_layout']['probe']['fragments_total']):>22}")
    print(f"{'month agg wall (s)':<32} {results['month_layout']['month_agg']['wall_s']:>16.4f} {results['trap_layout']['month_agg']['wall_s']:>22.4f}")
    print()
    print(f"results written to {RESULTS_PATH}")


if __name__ == "__main__":
    try:
        sys.exit(main())
    except NotImplementedError as e:
        fail(f"scaffold not implemented yet: {e}")
    except SystemExit:
        raise
    except Exception as e:
        fail(f"unexpected error: {type(e).__name__}: {e}")
