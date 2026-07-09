"""Validator for 07-duckdb-taste.

Run from the module root:
    uv run python 07-duckdb-taste/tests/validate.py
"""

import json
import re
import sys
from pathlib import Path

import duckdb

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

QUERIES_DIR = TASK_ROOT / "src" / "queries"
LAKE_DIR = DATA_DIR / "lake"
RESULTS_PATH = TASK_ROOT / "results-local.json"
PROFILE_PATH = TASK_ROOT / "results-local.profile.json"
NOTES_PATH = TASK_ROOT / "NOTES.md"


def strip_sql_comments(text):
    lines = [ln for ln in text.splitlines() if ln.strip() and not ln.strip().startswith("--")]
    return "\n".join(lines).strip()


def load_query(name):
    path = QUERIES_DIR / name
    if not path.exists():
        fail(f"missing query file {path}")
    body = strip_sql_comments(path.read_text(encoding="utf-8"))
    if not body:
        fail(f"{name} not implemented yet -- still just the TODO placeholder")
    return body


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
    row = con.execute(sql).fetchone()
    if row is None or len(row) < 2:
        fail("probe.sql did not return a (row_count, price_sum) row")
    row_count, price_sum = row[0], row[1]

    fp = gt["filter_probe"]
    if row_count != fp["rows"]:
        fail(f"probe.sql: row_count={row_count}, expected {fp['rows']} (data/ground-truth.json filter_probe)")
    approx(price_sum, fp["price_sum"], rel_tol=1e-6, what="probe.sql price_sum")


def check_latest_prices(con, gt):
    sql = load_query("latest_prices.sql")
    rows = con.execute(sql).fetchall()
    if not rows:
        fail("latest_prices.sql returned no rows")

    by_product = {}
    for product_id, captured_at_epoch, price in rows:
        by_product[int(product_id)] = (int(captured_at_epoch), price)

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


def parse_files_read(con, pruning_sql):
    match = re.match(r"(?is)^\s*EXPLAIN\s+ANALYZE\s*(.*)$", pruning_sql)
    if not match:
        fail("pruning_proof.sql must start with EXPLAIN ANALYZE")
    inner_sql = match.group(1).strip()
    if not inner_sql:
        fail("pruning_proof.sql has EXPLAIN ANALYZE but no query after it")

    if PROFILE_PATH.exists():
        PROFILE_PATH.unlink()
    con.execute("PRAGMA enable_profiling='json'")
    con.execute(f"PRAGMA profiling_output='{PROFILE_PATH.as_posix()}'")
    try:
        con.execute(inner_sql).fetchall()
    finally:
        con.execute("PRAGMA disable_profiling")

    if not PROFILE_PATH.exists():
        fail("DuckDB did not write a profiling output file -- unexpected duckdb version behavior")
    profile = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    PROFILE_PATH.unlink()

    files_read = 0
    found = False

    def walk(node):
        nonlocal files_read, found
        info = node.get("extra_info", {})
        if info.get("Function") == "READ_PARQUET" and "Total Files Read" in info:
            files_read += int(info["Total Files Read"])
            found = True
        for child in node.get("children", []):
            walk(child)

    walk(profile)
    if not found:
        fail("could not find a READ_PARQUET 'Total Files Read' entry in the EXPLAIN ANALYZE plan")
    return files_read


def covered_months(date_from, date_to):
    from datetime import datetime, timezone

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


def check_pruning(con, gt):
    sql = load_query("pruning_proof.sql")
    files_read = parse_files_read(con, sql)

    fp = gt["filter_probe"]
    months = covered_months(fp["captured_at_from"], fp["captured_at_to"])
    files_in_probe_months = sum(1 for m in months for _ in (LAKE_DIR / f"month={m}").glob("*.parquet"))
    files_total_lake = sum(1 for _ in LAKE_DIR.glob("month=*/*.parquet"))

    if files_in_probe_months == 0:
        fail(f"no Parquet files found on disk under {months} -- is data/lake built?")

    if files_read > files_in_probe_months:
        fail(
            f"pruning_proof.sql read {files_read} files, but only {files_in_probe_months} "
            f"files physically exist in {months} -- add a filter on the `month` partition "
            "column so DuckDB can prune before opening files"
        )
    if files_read >= files_total_lake:
        fail(
            f"pruning_proof.sql read {files_read} files out of {files_total_lake} total in "
            "the lake -- that's a full scan, not a pruned one. Filter on `month`, not just "
            "on captured_at"
        )


@guarded
def main():
    if not LAKE_DIR.exists():
        fail(f"no lake at {LAKE_DIR} -- task 04 (partitioned-datasets) must be built first")

    gt = load_ground_truth()
    con = duckdb.connect()
    con.execute("SET TimeZone='UTC'")

    check_monthly_rollup(con, gt)
    check_probe(con, gt)
    check_latest_prices(con, gt)
    check_pruning(con, gt)

    load_results(RESULTS_PATH, what="results-local.json (run tests/bench.py first)")

    check_notes_filled(NOTES_PATH)

    passed("monthly_rollup, probe, latest_prices all match ground truth; pruning_proof.sql shows real partition pruning")


if __name__ == "__main__":
    main()
