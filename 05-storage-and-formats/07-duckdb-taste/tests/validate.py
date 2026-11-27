"""Validator for 07-duckdb-taste.

Run from the module root:
    uv run python 07-duckdb-taste/tests/validate.py
"""

import sys
from pathlib import Path

import duckdb

from bench import covered_months, load_query, parse_explain_analyze

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))

from harness.common import (  # noqa: E402
    DATA_DIR,
    approx,
    check_notes_filled,
    fail,
    guarded,
    load_ground_truth,
    load_results,
    passed,
)

LAKE_DIR = DATA_DIR / "lake"
RESULTS_PATH = TASK_ROOT / "results-local.json"
NOTES_PATH = TASK_ROOT / "NOTES.md"


def check_monthly_rollup(con, gt):
    sql = load_query("monthly_rollup.sql")
    rows = con.execute(sql).fetchall()
    if not rows:
        fail("monthly_rollup.sql returned no rows")

    months_expected = sorted(gt["rows_by_month"].keys())
    if len(rows) != len(months_expected):
        fail(f"monthly_rollup.sql: expected {len(months_expected)} rows (one per month), got {len(rows)}")

    seen_months = [r[0] for r in rows]
    if seen_months != sorted(seen_months):
        fail(f"monthly_rollup.sql: rows are not ordered by month ascending -- got {seen_months}")
    if seen_months != months_expected:
        fail(f"monthly_rollup.sql: month values don't match ground truth -- got {seen_months}, expected {months_expected}")

    for month, row_count, price_sum in rows:
        exp_count = gt["rows_by_month"][month]
        exp_sum = gt["price_sum_by_month"][month]
        if row_count != exp_count:
            fail(f"monthly_rollup.sql[{month}]: row_count={row_count}, expected {exp_count}")
        approx(price_sum, exp_sum, rel_tol=1e-6, what=f"monthly_rollup.sql[{month}] price_sum")


def check_probe(con, gt):
    sql = load_query("probe.sql")
    rows = con.execute(sql).fetchall()
    if len(rows) != 1 or len(rows[0]) != 2:
        fail("probe.sql must return one (row_count, price_sum) row")
    row_count, price_sum = rows[0]

    fp = gt["filter_probe"]
    if row_count != fp["rows"]:
        fail(f"probe.sql: row_count={row_count}, expected {fp['rows']} (data/ground-truth.json filter_probe)")
    approx(price_sum, fp["price_sum"], rel_tol=1e-6, what="probe.sql price_sum")
    return sql


def check_latest_prices(con, gt):
    sql = load_query("latest_prices.sql")
    rows = con.execute(sql).fetchall()
    if not rows:
        fail("latest_prices.sql returned no rows")

    by_product = {}
    for product_id, captured_at_epoch, price in rows:
        if product_id is None or captured_at_epoch is None or price is None:
            fail("latest_prices.sql must return a product ID, epoch, and non-null price in every row")
        if product_id in by_product:
            fail(f"latest_prices.sql returned more than one row for product_id {product_id}")
        by_product[product_id] = (captured_at_epoch, price)

    lake_glob = (LAKE_DIR / "month=*" / "*.parquet").as_posix()
    expected_ids = {
        pid
        for (pid,) in con.execute(
            "SELECT DISTINCT product_id FROM read_parquet(?) WHERE price IS NOT NULL",
            [lake_glob],
        ).fetchall()
    }
    missing = expected_ids - by_product.keys()
    extra = by_product.keys() - expected_ids
    if missing or extra:
        fail(f"latest_prices.sql product coverage: {len(missing)} missing IDs and {len(extra)} unexpected IDs")

    for pid_str, expected in gt["latest_price_probe"].items():
        pid = int(pid_str)
        if pid not in by_product:
            fail(f"latest_prices.sql: no row for product_id {pid} (expected in data/ground-truth.json)")
        epoch_s, price = by_product[pid]
        if epoch_s != expected["captured_at_epoch"]:
            fail(
                f"latest_prices.sql[{pid}]: captured_at_epoch={epoch_s}, "
                f"expected {expected['captured_at_epoch']}"
            )
        approx(price, expected["price"], rel_tol=1e-6, what=f"latest_prices.sql[{pid}] price")


def check_pruning(con, gt, probe_sql):
    sql = load_query("pruning_proof.sql")
    fp = gt["filter_probe"]
    months = covered_months(fp["captured_at_from"], fp["captured_at_to"])
    parse_explain_analyze(con, sql, probe_sql, LAKE_DIR, months)


@guarded
def main():
    if not LAKE_DIR.exists():
        fail(f"no lake at {LAKE_DIR} -- task 04 (partitioned-datasets) must be built first")

    gt = load_ground_truth()
    con = duckdb.connect()
    con.execute("SET TimeZone='UTC'")

    check_monthly_rollup(con, gt)
    probe_sql = check_probe(con, gt)
    check_latest_prices(con, gt)
    check_pruning(con, gt, probe_sql)

    load_results(RESULTS_PATH, what="results-local.json (run tests/bench.py first)")

    check_notes_filled(NOTES_PATH)

    passed("monthly_rollup, probe, latest_prices all match ground truth; pruning_proof.sql shows real partition pruning")


if __name__ == "__main__":
    main()
