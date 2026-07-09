"""Validator for the format shootout.

Checks (see 01-format-shootout/README.md, "Completion criteria"):

- data/formats/snapshots.parquet and .csv exist, results-local.json is complete
- Parquet correctness vs data/ground-truth.json: row count, per-currency
  counts, per-month price sums, distinct product count
- CSV correctness vs ground truth: row count, total price sum
- Parquet schema: captured_at is a UTC timestamp type, price has nulls
- relative targets: parquet size <= 35% of raw JSONL size; reading only the
  price column from Parquet is >= 5x faster than a full CSV scan

Usage (from module root):
    uv run python 01-format-shootout/tests/validate.py
"""

import sys
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
TASK_ROOT = TESTS_DIR.parent
MODULE_ROOT = TASK_ROOT.parent

sys.path.insert(0, str(MODULE_ROOT / "harness"))
import common  # noqa: E402

RESULTS_PATH = TASK_ROOT / "results-local.json"
FORMATS_DIR = common.DATA_DIR / "formats"
PARQUET_PATH = FORMATS_DIR / "snapshots.parquet"
CSV_PATH = FORMATS_DIR / "snapshots.csv"

PARQUET_SIZE_RATIO_MAX = 0.35
COLUMN_READ_SPEEDUP_MIN = 5.0


@common.guarded
def main():
    if not PARQUET_PATH.exists():
        common.fail(f"missing {PARQUET_PATH} -- run tests/bench.py first")
    if not CSV_PATH.exists():
        common.fail(f"missing {CSV_PATH} -- run tests/bench.py first")

    results = common.load_results(RESULTS_PATH, what="bench results")
    for fmt in ("raw_jsonl", "csv", "parquet"):
        if fmt not in results:
            common.fail(f"results-local.json missing '{fmt}' section -- re-run tests/bench.py")
    for fmt, keys in (
        ("raw_jsonl", ("size_bytes", "full_scan_seconds")),
        ("csv", ("size_bytes", "rows", "full_scan_seconds", "column_read_seconds")),
        ("parquet", ("size_bytes", "rows", "full_scan_seconds", "column_read_seconds")),
    ):
        for k in keys:
            if k not in results[fmt]:
                common.fail(f"results-local.json['{fmt}'] missing '{k}' -- re-run tests/bench.py")

    gt = common.load_ground_truth()

    import duckdb
    import pyarrow.parquet as pq

    con = duckdb.connect()
    con.execute("SET TimeZone='UTC'")  # session tz affects strftime() on timestamptz columns

    # --- Parquet correctness -------------------------------------------------
    row = con.execute(
        "SELECT count(*), count(DISTINCT product_id) FROM read_parquet(?)", [str(PARQUET_PATH)]
    ).fetchone()
    parquet_rows, parquet_distinct = row
    if parquet_rows != gt["total_rows"]:
        common.fail(f"parquet row count: expected {gt['total_rows']}, got {parquet_rows}")
    if parquet_distinct != gt["distinct_products"]:
        common.fail(
            f"parquet distinct product count: expected {gt['distinct_products']}, got {parquet_distinct}"
        )

    cur_rows = con.execute(
        "SELECT currency, count(*) FROM read_parquet(?) GROUP BY currency", [str(PARQUET_PATH)]
    ).fetchall()
    cur_counts = {c: n for c, n in cur_rows}
    for currency, expected in gt["currency_counts"].items():
        actual = cur_counts.get(currency, 0)
        if actual != expected:
            common.fail(f"parquet currency_counts[{currency}]: expected {expected}, got {actual}")

    month_rows = con.execute(
        """
        SELECT strftime(captured_at, '%Y-%m') AS ym, sum(price)
        FROM read_parquet(?)
        WHERE price IS NOT NULL
        GROUP BY ym
        """,
        [str(PARQUET_PATH)],
    ).fetchall()
    month_sums = {ym: s for ym, s in month_rows}
    for month, expected in gt["price_sum_by_month"].items():
        actual = month_sums.get(month, 0.0)
        common.approx(actual, expected, rel_tol=1e-6, what=f"parquet price_sum_by_month[{month}]")

    price_null_count = con.execute(
        "SELECT count(*) - count(price) FROM read_parquet(?)", [str(PARQUET_PATH)]
    ).fetchone()[0]
    if price_null_count <= 0:
        common.fail("parquet: price column has no nulls -- non-200 rows must carry null price")

    # --- Parquet schema -------------------------------------------------------
    schema = pq.ParquetFile(PARQUET_PATH).schema_arrow
    captured_field = schema.field("captured_at")
    import pyarrow as pa

    if not pa.types.is_timestamp(captured_field.type):
        common.fail(f"parquet captured_at: expected a timestamp type, got {captured_field.type}")
    if captured_field.type.tz not in ("UTC", "utc"):
        common.fail(f"parquet captured_at: expected tz=UTC, got tz={captured_field.type.tz!r}")
    if captured_field.type.unit not in ("us", "ns"):
        common.fail(f"parquet captured_at: expected unit us or ns, got {captured_field.type.unit!r}")

    # --- CSV correctness --------------------------------------------------------
    csv_row = con.execute(
        "SELECT count(*), sum(price) FROM read_csv(?, all_varchar=false)", [str(CSV_PATH)]
    ).fetchone()
    csv_rows, csv_price_sum = csv_row
    if csv_rows != gt["total_rows"]:
        common.fail(f"csv row count: expected {gt['total_rows']}, got {csv_rows}")
    expected_total_price_sum = sum(gt["price_sum_by_month"].values())
    common.approx(csv_price_sum, expected_total_price_sum, rel_tol=1e-6, what="csv total price sum")

    # --- Relative targets ---------------------------------------------------
    raw_size = results["raw_jsonl"]["size_bytes"]
    parquet_size = results["parquet"]["size_bytes"]
    ratio = parquet_size / raw_size
    if ratio > PARQUET_SIZE_RATIO_MAX:
        common.fail(
            f"parquet size ratio {ratio:.3f} exceeds max {PARQUET_SIZE_RATIO_MAX} "
            f"(parquet={parquet_size} bytes, raw jsonl={raw_size} bytes)"
        )

    csv_full_scan = results["csv"]["full_scan_seconds"]
    parquet_col_read = results["parquet"]["column_read_seconds"]
    speedup = csv_full_scan / max(parquet_col_read, 1e-9)
    if speedup < COLUMN_READ_SPEEDUP_MIN:
        common.fail(
            f"parquet single-column read only {speedup:.1f}x faster than full CSV scan "
            f"(need >= {COLUMN_READ_SPEEDUP_MIN}x); csv_full_scan={csv_full_scan:.3f}s, "
            f"parquet_column_read={parquet_col_read:.3f}s"
        )

    common.passed(
        f"parquet/raw size ratio {ratio:.3f}, column-read speedup {speedup:.1f}x"
    )


if __name__ == "__main__":
    main()
