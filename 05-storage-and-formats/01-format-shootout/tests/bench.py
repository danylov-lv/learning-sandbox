"""Benchmark harness for the format shootout (infrastructure, not learner code).

Runs the learner's two converters (src/convert_parquet.py, src/convert_csv.py),
times the conversions, then measures for each of JSONL / CSV / Parquet:

- file size on disk (JSONL: sum of data/raw/part-*.jsonl)
- full-scan time (read every row, touch one numeric field)
- single-column read time (read just `price`)

Writes 01-format-shootout/results-local.json and prints a small table.

Usage (from module root):
    uv run python 01-format-shootout/tests/bench.py
"""

import csv
import json
import sys
import time
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
TASK_ROOT = TESTS_DIR.parent
MODULE_ROOT = TASK_ROOT.parent

sys.path.insert(0, str(MODULE_ROOT / "harness"))
import common  # noqa: E402

SRC_DIR = TASK_ROOT / "src"
RESULTS_PATH = TASK_ROOT / "results-local.json"
FORMATS_DIR = common.DATA_DIR / "formats"
PARQUET_PATH = FORMATS_DIR / "snapshots.parquet"
CSV_PATH = FORMATS_DIR / "snapshots.csv"


def raw_jsonl_size():
    return sum(p.stat().st_size for p in sorted(common.RAW_DIR.glob("part-*.jsonl")))


def run_convert(mod_path, mod_name, out_path):
    mod = common.load_learner_module(mod_path, mod_name)
    if not hasattr(mod, "convert"):
        common.fail(f"{mod_path.name} does not define convert(raw_dir, out_path)")
    t0 = time.time()
    try:
        rows = mod.convert(common.RAW_DIR, out_path)
    except NotImplementedError:
        common.fail("scaffold not implemented yet")
    except SystemExit:
        raise
    except Exception as e:
        common.fail(f"{mod_path.name}: convert() raised {type(e).__name__}: {e}")
    elapsed = time.time() - t0
    if not out_path.exists():
        common.fail(f"{mod_path.name}: convert() returned but {out_path} does not exist")
    return rows, elapsed


def scan_jsonl_full():
    """Stream every raw JSONL line, sum `price` treating null as 0.0. Bounded memory."""
    total = 0.0
    rows = 0
    t0 = time.time()
    for p in sorted(common.RAW_DIR.glob("part-*.jsonl")):
        with open(p, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                price = obj.get("price")
                total += price if price is not None else 0.0
                rows += 1
    return time.time() - t0, rows, total


def scan_csv_full(path):
    total = 0.0
    rows = 0
    t0 = time.time()
    with open(path, "r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            price = row.get("price")
            total += float(price) if price not in (None, "") else 0.0
            rows += 1
    elapsed = time.time() - t0
    return elapsed, rows, total


def scan_csv_column(path):
    """Full parse then pick one column -- CSV cannot skip columns while scanning rows."""
    return scan_csv_full(path)


def scan_parquet_full(path):
    import pyarrow.parquet as pq

    t0 = time.time()
    table = pq.read_table(path)
    elapsed = time.time() - t0
    return elapsed, table.num_rows


def scan_parquet_column(path):
    import pyarrow.parquet as pq

    t0 = time.time()
    table = pq.read_table(path, columns=["price"])
    elapsed = time.time() - t0
    return elapsed, table.num_rows


def main():
    FORMATS_DIR.mkdir(parents=True, exist_ok=True)

    raw_size = raw_jsonl_size()
    if raw_size == 0:
        common.fail(f"no raw JSONL found under {common.RAW_DIR} -- run generate.py first")

    print("converting to Parquet...")
    parquet_rows, parquet_convert_s = run_convert(
        SRC_DIR / "convert_parquet.py", "convert_parquet", PARQUET_PATH
    )
    print(f"  {parquet_rows:,} rows in {parquet_convert_s:.1f}s")

    print("converting to CSV...")
    csv_rows, csv_convert_s = run_convert(
        SRC_DIR / "convert_csv.py", "convert_csv", CSV_PATH
    )
    print(f"  {csv_rows:,} rows in {csv_convert_s:.1f}s")

    print("scanning JSONL (streaming)...")
    jsonl_full_s, jsonl_rows, _ = scan_jsonl_full()

    print("scanning CSV (full)...")
    csv_full_s, _, _ = scan_csv_full(CSV_PATH)

    print("scanning CSV (single column, still full parse)...")
    csv_col_s, _, _ = scan_csv_column(CSV_PATH)

    print("scanning Parquet (full)...")
    parquet_full_s, _ = scan_parquet_full(PARQUET_PATH)

    print("scanning Parquet (single column)...")
    parquet_col_s, _ = scan_parquet_column(PARQUET_PATH)

    parquet_size = PARQUET_PATH.stat().st_size
    csv_size = CSV_PATH.stat().st_size

    results = {
        "raw_jsonl": {
            "size_bytes": raw_size,
            "rows": jsonl_rows,
            "full_scan_seconds": jsonl_full_s,
            "column_read_seconds": jsonl_full_s,  # JSONL cannot skip fields either
        },
        "csv": {
            "size_bytes": csv_size,
            "rows": csv_rows,
            "convert_seconds": csv_convert_s,
            "full_scan_seconds": csv_full_s,
            "column_read_seconds": csv_col_s,
        },
        "parquet": {
            "size_bytes": parquet_size,
            "rows": parquet_rows,
            "convert_seconds": parquet_convert_s,
            "full_scan_seconds": parquet_full_s,
            "column_read_seconds": parquet_col_s,
        },
    }
    RESULTS_PATH.write_text(json.dumps(results, indent=2), encoding="utf-8")

    print()
    print(f"{'format':<10}{'size (MB)':>12}{'full scan (s)':>16}{'1 col (s)':>12}")
    print(f"{'jsonl':<10}{raw_size / 1e6:>12.1f}{jsonl_full_s:>16.2f}{jsonl_full_s:>12.2f}")
    print(f"{'csv':<10}{csv_size / 1e6:>12.1f}{csv_full_s:>16.2f}{csv_col_s:>12.2f}")
    print(f"{'parquet':<10}{parquet_size / 1e6:>12.1f}{parquet_full_s:>16.2f}{parquet_col_s:>12.2f}")
    print()
    print(f"results written to {RESULTS_PATH}")


if __name__ == "__main__":
    main()
