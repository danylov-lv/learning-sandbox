"""Checker for 01-read-the-plan.

Run from the module root:
    uv run python 01-read-the-plan/tests/check.py
"""

import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

import psycopg  # noqa: E402

from plan_check import PlanAssertionError, forbid_node, get_plan, require_node  # noqa: E402
import baseline  # noqa: E402

MODULE_ROOT = Path(__file__).resolve().parents[2]
QUERY_FILE = MODULE_ROOT / "queries" / "q01.sql"
BASELINE_FILE = MODULE_ROOT / "baseline-local.json"
QUERY_ID = "q01"
MIN_SPEEDUP = 50.0


def main():
    sql = QUERY_FILE.read_text(encoding="utf-8")

    try:
        plan = get_plan(sql)
    except psycopg.Error as e:
        print(f"NOT PASSED: could not run query: {e}")
        sys.exit(1)

    try:
        forbid_node(plan, "Seq Scan", table="orders")
        print("PASS  no Seq Scan on orders")
    except PlanAssertionError as e:
        print(f"FAIL  {e}")
        print(f"NOT PASSED: {e}")
        sys.exit(1)

    try:
        require_node(plan, "Index Scan", table="orders")
        print("PASS  orders reached via an index")
    except PlanAssertionError as e:
        print(f"FAIL  {e}")
        print(f"NOT PASSED: {e}")
        sys.exit(1)

    if not BASELINE_FILE.exists() or QUERY_ID not in baseline.load_baseline(BASELINE_FILE):
        reason = f"record the baseline first: uv run python tools/baseline.py record queries/{QUERY_ID}.sql"
        print(f"NOT PASSED: {reason}")
        sys.exit(1)

    data = baseline.load_baseline(BASELINE_FILE)
    base_ms = data[QUERY_ID]["median_ms"]
    try:
        timings = baseline.time_query(sql, runs=5, warmups=1)
    except psycopg.Error as e:
        print(f"NOT PASSED: timing run failed: {e}")
        sys.exit(1)

    median = statistics.median(timings)
    speedup = base_ms / median if median > 0 else float("inf")
    if speedup >= MIN_SPEEDUP:
        print(f"PASS  {median:.2f} ms vs baseline {base_ms:.2f} ms -> {speedup:.1f}x speedup (required >= {MIN_SPEEDUP}x)")
    else:
        reason = (
            f"{median:.2f} ms vs baseline {base_ms:.2f} ms -> only {speedup:.1f}x speedup "
            f"(required >= {MIN_SPEEDUP}x)"
        )
        print(f"FAIL  {reason}")
        print(f"NOT PASSED: {reason}")
        sys.exit(1)

    print("PASSED")
    sys.exit(0)


if __name__ == "__main__":
    main()
