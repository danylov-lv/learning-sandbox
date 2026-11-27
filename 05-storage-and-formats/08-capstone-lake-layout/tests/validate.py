"""Validator for the capstone lake layout.

Three checkpoints (see README.md):

--cp1   builds the lake by calling the learner's src/build_capstone.py
        `build(raw_dir, out_dir)`, then checks: bronze row count ==
        total_rows; silver row count == total_rows; per-month price sums
        match ground truth (rel_tol 1e-6); silver partitions exactly match
        rows_by_month's keys.

--cp2   structural gates on the already-built silver zone: every file
        zstd-compressed; <= 8 files per partition; no file smaller than
        min(8 MB, partition_bytes / 2) except the last file of a
        partition; rows are sorted within each partition; <= 15% of silver
        row groups overlap the filter_probe;
        a DuckDB smoke query reproduces latest_price_probe.

--cp3   DESIGN.md is filled in with real content (length check on
        non-heading text, >= 1500 chars).

No flags: run all three in order, stop at the first failure.

Usage (from module root):
    uv run python 08-capstone-lake-layout/tests/validate.py [--cp1] [--cp2] [--cp3]
"""

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
TASK_ROOT = TESTS_DIR.parent
MODULE_ROOT = TASK_ROOT.parent

sys.path.insert(0, str(MODULE_ROOT / "harness"))
import common  # noqa: E402

SRC_DIR = TASK_ROOT / "src"
DESIGN_PATH = TASK_ROOT / "DESIGN.md"
LAKE_DIR = common.DATA_DIR / "capstone-lake"
BRONZE_DIR = LAKE_DIR / "bronze"
SILVER_DIR = LAKE_DIR / "silver"

MAX_FILES_PER_PARTITION = 8
MIN_FILE_SIZE_FLOOR = 8_000_000  # 8 MB
MAX_PRUNING_OVERLAP_FRACTION = 0.15
DESIGN_MIN_CHARS = 1500


def _fail_cp(cp, reason):
    print(f"NOT PASSED [{cp}]: {reason}")
    sys.exit(1)


def _silver_partitions():
    if not SILVER_DIR.exists():
        return []
    return sorted(p for p in SILVER_DIR.iterdir() if p.is_dir() and p.name.startswith("month="))


def _silver_files(partition_dir):
    return sorted(partition_dir.glob("*.parquet"))


def run_cp1():
    gt = common.load_ground_truth()

    mod = common.load_learner_module(SRC_DIR / "build_capstone.py", "build_capstone")
    if not hasattr(mod, "build"):
        _fail_cp("cp1", "build_capstone.py does not define build(raw_dir, out_dir)")

    print("building lake (src/build_capstone.py build())...")
    try:
        manifest = mod.build(common.RAW_DIR, LAKE_DIR)
    except NotImplementedError:
        _fail_cp("cp1", "scaffold not implemented yet (NotImplementedError)")
    except Exception as e:
        _fail_cp("cp1", f"build() raised {type(e).__name__}: {e}")

    if not isinstance(manifest, dict):
        _fail_cp("cp1", f"build() must return a dict manifest, got {type(manifest).__name__}")
    for zone in ("bronze", "silver"):
        if zone not in manifest:
            _fail_cp("cp1", f"manifest missing '{zone}' zone entry")

    import duckdb

    con = duckdb.connect()
    con.execute("SET TimeZone='UTC'")

    # --- bronze round-trip: all rows preserved -------------------------------
    if not BRONZE_DIR.exists():
        _fail_cp("cp1", f"missing bronze zone at {BRONZE_DIR}")
    bronze_files = sorted(BRONZE_DIR.rglob("*.parquet"))
    if not bronze_files:
        _fail_cp("cp1", f"no parquet files found under {BRONZE_DIR}")
    bronze_glob = str(BRONZE_DIR / "**" / "*.parquet")
    bronze_rows = con.execute(
        "SELECT count(*) FROM read_parquet(?, hive_partitioning=false)", [bronze_glob]
    ).fetchone()[0]
    if bronze_rows != gt["total_rows"]:
        _fail_cp(
            "cp1",
            f"bronze row count: expected {gt['total_rows']}, got {bronze_rows}",
        )

    # --- silver structure -----------------------------------------------------
    partitions = _silver_partitions()
    if not partitions:
        _fail_cp("cp1", f"no month=* partitions found under {SILVER_DIR}")

    actual_months = {p.name.split("=", 1)[1] for p in partitions}
    expected_months = set(gt["rows_by_month"].keys())
    if actual_months != expected_months:
        missing = expected_months - actual_months
        extra = actual_months - expected_months
        _fail_cp(
            "cp1",
            f"silver partitions mismatch -- missing {sorted(missing)}, unexpected {sorted(extra)}",
        )

    silver_glob = str(SILVER_DIR / "**" / "*.parquet")
    month_rows = con.execute(
        """
        SELECT month, count(*), coalesce(sum(price), 0.0),
               count(*) FILTER (WHERE strftime(captured_at, '%Y-%m') IS DISTINCT FROM month)
        FROM read_parquet(?, hive_partitioning=true)
        GROUP BY month
        """,
        [silver_glob],
    ).fetchall()
    silver_rows = 0
    for month, rows, price_sum, misplaced_rows in month_rows:
        if misplaced_rows:
            _fail_cp("cp1", f"month={month} has {misplaced_rows} rows outside its UTC month")
        expected_rows = gt["rows_by_month"].get(month)
        if rows != expected_rows:
            _fail_cp("cp1", f"month={month}: expected {expected_rows} rows, got {rows}")
        silver_rows += rows
        expected = gt["price_sum_by_month"].get(month, 0.0)
        common.approx(price_sum, expected, rel_tol=1e-6, what=f"silver price_sum_by_month[{month}]")
    if silver_rows != gt["total_rows"]:
        _fail_cp("cp1", f"silver row count: expected {gt['total_rows']}, got {silver_rows}")

    print(f"PASSED [cp1]: bronze {bronze_rows} rows, silver {silver_rows} rows across {len(partitions)} partitions")
    return True


def file_sort_bounds(parquet_file, path):
    from pyarrow import timestamp

    expected_timestamp = timestamp("us", tz="UTC")
    first_key = last_key = None
    for batch in parquet_file.iter_batches(columns=["source_id", "captured_at"]):
        source_ids = batch.column("source_id").to_pylist()
        captured_at = batch.column("captured_at").cast(expected_timestamp).cast("int64").to_pylist()
        for key in zip(source_ids, captured_at):
            if None in key:
                _fail_cp("cp2", f"{path}: null value in (source_id, captured_at) sort key")
            if last_key is not None and key < last_key:
                _fail_cp("cp2", f"{path}: rows are out of order by (source_id, captured_at)")
            if first_key is None:
                first_key = key
            last_key = key
    return first_key, last_key


def run_cp2():
    gt = common.load_ground_truth()

    partitions = _silver_partitions()
    if not partitions:
        _fail_cp("cp2", f"no silver partitions found under {SILVER_DIR} -- run --cp1 first")

    import pyarrow.parquet as pq

    total_row_groups = 0
    overlapping_row_groups = 0

    fp = gt["filter_probe"]
    probe_source_id = fp["source_id"]
    probe_from = datetime.strptime(fp["captured_at_from"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    probe_to_exclusive = datetime.strptime(fp["captured_at_to"], "%Y-%m-%d").replace(
        tzinfo=timezone.utc
    ) + timedelta(days=1)

    for part_dir in partitions:
        files = _silver_files(part_dir)
        if not files:
            _fail_cp("cp2", f"partition {part_dir.name} has no parquet files")
        if len(files) > MAX_FILES_PER_PARTITION:
            _fail_cp(
                "cp2",
                f"partition {part_dir.name} has {len(files)} files "
                f"(max {MAX_FILES_PER_PARTITION})",
            )

        sizes = [(f, f.stat().st_size) for f in files]
        partition_bytes = sum(s for _, s in sizes)
        min_size_required = min(MIN_FILE_SIZE_FLOOR, partition_bytes / 2)
        # last file (by filename order) is exempt -- expected partial cutover file
        for f, size in sizes[:-1]:
            if size < min_size_required:
                _fail_cp(
                    "cp2",
                    f"{part_dir.name}/{f.name} is {size} bytes, below "
                    f"min(8MB, partition_bytes/2) = {min_size_required:.0f} bytes",
                )

        file_ranges = []
        for f, _ in sizes:
            pf = pq.ParquetFile(f)
            first_key, last_key = file_sort_bounds(pf, f)
            if first_key is not None:
                file_ranges.append((first_key, last_key, f))
            meta = pf.metadata
            for rgi in range(meta.num_row_groups):
                rg = meta.row_group(rgi)
                total_row_groups += 1

                src_stats = None
                cap_stats = None
                overlap = True
                for ci in range(rg.num_columns):
                    col = rg.column(ci)
                    if col.compression.upper() != "ZSTD":
                        _fail_cp(
                            "cp2",
                            f"{part_dir.name}/{f.name}: column "
                            f"'{col.path_in_schema}' compression is "
                            f"{col.compression}, expected ZSTD",
                        )
                    if col.path_in_schema == "source_id":
                        src_stats = col.statistics
                    elif col.path_in_schema == "captured_at":
                        cap_stats = col.statistics

                if src_stats is not None and src_stats.has_min_max:
                    if src_stats.max < probe_source_id or src_stats.min > probe_source_id:
                        overlap = False
                if cap_stats is not None and cap_stats.has_min_max:
                    if cap_stats.max < probe_from or cap_stats.min >= probe_to_exclusive:
                        overlap = False

                if overlap:
                    overlapping_row_groups += 1

        file_ranges.sort()
        for (_, previous_last, previous_file), (first, _, file) in zip(file_ranges, file_ranges[1:]):
            if previous_last > first:
                _fail_cp(
                    "cp2",
                    f"{part_dir.name}: (source_id, captured_at) ranges overlap between "
                    f"{previous_file.name} and {file.name}",
                )

    if total_row_groups == 0:
        _fail_cp("cp2", "no row groups found in silver zone")

    frac = overlapping_row_groups / total_row_groups
    if frac > MAX_PRUNING_OVERLAP_FRACTION:
        _fail_cp(
            "cp2",
            f"{overlapping_row_groups}/{total_row_groups} = {frac:.3f} of row groups "
            f"overlap the filter_probe range (max {MAX_PRUNING_OVERLAP_FRACTION})",
        )

    import duckdb

    con = duckdb.connect()
    silver_glob = str(SILVER_DIR / "**" / "*.parquet")

    for pid_str, expected in gt["latest_price_probe"].items():
        pid = int(pid_str)
        row = con.execute(
            """
            SELECT epoch_us(captured_at) // 1000000, price
            FROM read_parquet(?, hive_partitioning=true)
            WHERE product_id = ? AND price IS NOT NULL
            ORDER BY captured_at DESC
            LIMIT 1
            """,
            [silver_glob, pid],
        ).fetchone()
        if row is None:
            _fail_cp("cp2", f"latest_price_probe: no rows found for product_id {pid}")
        actual_epoch, price = row
        if actual_epoch != expected["captured_at_epoch"]:
            _fail_cp(
                "cp2",
                f"latest_price_probe[{pid}]: expected captured_at_epoch "
                f"{expected['captured_at_epoch']}, got {actual_epoch}",
            )
        common.approx(
            price, expected["price"], rel_tol=1e-6, what=f"latest_price_probe[{pid}] price"
        )

    print(
        f"PASSED [cp2]: {overlapping_row_groups}/{total_row_groups} row groups overlap "
        f"filter_probe ({frac:.3f}), silver is sorted and all files meet codec, count and size gates"
    )
    return True


def run_cp3():
    if not DESIGN_PATH.exists():
        _fail_cp("cp3", f"missing {DESIGN_PATH}")
    text = DESIGN_PATH.read_text(encoding="utf-8")
    non_heading = "\n".join(
        line for line in text.splitlines() if not line.strip().startswith("#")
    ).strip()
    if len(non_heading) < DESIGN_MIN_CHARS:
        _fail_cp(
            "cp3",
            f"DESIGN.md still looks like the empty template "
            f"({len(non_heading)} non-heading chars, need >= {DESIGN_MIN_CHARS})",
        )
    print(f"PASSED [cp3]: DESIGN.md has {len(non_heading)} non-heading chars")
    return True


@common.guarded
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cp1", action="store_true")
    ap.add_argument("--cp2", action="store_true")
    ap.add_argument("--cp3", action="store_true")
    args = ap.parse_args()

    selected = [flag for flag in (args.cp1, args.cp2, args.cp3) if flag]
    run_all = not selected

    if run_all or args.cp1:
        run_cp1()
    if run_all or args.cp2:
        run_cp2()
    if run_all or args.cp3:
        run_cp3()

    common.passed("cp1, cp2, cp3" if run_all else "requested checkpoints")


if __name__ == "__main__":
    main()
