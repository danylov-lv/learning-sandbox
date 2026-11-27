"""Verify vacuum hygiene and report its effect on the task-04 plan."""

import sys
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(MODULE_ROOT / "tools"))

import psycopg  # noqa: E402

from plan_check import conninfo, find_nodes, get_plan  # noqa: E402
from vacuum_check import check_vacuum_hygiene  # noqa: E402


def report_heap_fetches():
    sql = (MODULE_ROOT / "queries" / "q04.sql").read_text(encoding="utf-8")
    try:
        plan = get_plan(sql)
        hits = find_nodes(plan, "Index Only Scan", table="orders")
        for node in hits:
            print(
                f"info  orders Index Only Scan Heap Fetches: {node.get('Heap Fetches')} "
                f"(rows returned: {node.get('Actual Rows')})"
            )
        if not hits:
            print("info  q04 does not use an Index Only Scan on orders")
    except psycopg.Error as e:
        print(f"info  could not probe q04: {e}")


def main():
    try:
        with psycopg.connect(conninfo()) as conn, conn.cursor() as cur:
            failures = check_vacuum_hygiene(cur, report_details=True)
    except psycopg.Error as e:
        print(f"NOT PASSED: could not check database hygiene: {e}")
        sys.exit(1)

    report_heap_fetches()
    if failures:
        print(f"NOT PASSED: {'; '.join(failures)}")
        sys.exit(1)

    print("PASSED")


if __name__ == "__main__":
    main()
