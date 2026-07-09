"""Checker for 11-vacuum-debt.

Run from the module root:
    uv run python 11-vacuum-debt/tests/check.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

import psycopg  # noqa: E402

from plan_check import conninfo, find_nodes, get_plan  # noqa: E402

TABLES = ["orders", "payments", "inventory_events"]

# Ratio-based, not row-count-based, so this works against the live seeded DB
# (millions of rows) and a small scratch copy (a few hundred thousand rows)
# alike.
MAX_DEAD_RATIO = 0.02

# The task-04-shaped query. Reported as info only -- this task does not
# require task 04 to be done, but if a covering index on orders already
# makes this an Index Only Scan, the Heap Fetches count is the payoff of
# vacuuming: it should drop to ~0 once the visibility map is populated.
IOS_PROBE_SQL = """
SELECT created_at, status, total_amount
FROM orders
WHERE user_id = 42
  AND created_at >= now() - interval '365 days'
ORDER BY created_at DESC
LIMIT 25
"""


def table_stats(cur, table):
    cur.execute("SELECT reloptions FROM pg_class WHERE relname = %s", (table,))
    row = cur.fetchone()
    reloptions = row[0] if row and row[0] else []
    cur.execute(
        """
        SELECT n_live_tup, n_dead_tup, last_vacuum, last_autovacuum,
               pg_size_pretty(pg_total_relation_size(%s::regclass))
        FROM pg_stat_user_tables WHERE relname = %s
        """,
        (table, table),
    )
    row = cur.fetchone()
    if row is None:
        return None
    n_live, n_dead, last_vacuum, last_autovacuum, total_size = row
    return {
        "reloptions": reloptions,
        "n_live": n_live or 0,
        "n_dead": n_dead or 0,
        "last_vacuum": last_vacuum,
        "last_autovacuum": last_autovacuum,
        "total_size": total_size,
    }


def main():
    try:
        conn = psycopg.connect(conninfo())
    except psycopg.Error as e:
        print(f"NOT PASSED: could not connect to the database: {e}")
        sys.exit(1)

    failed = False
    reasons = []

    with conn.cursor() as cur:
        for table in TABLES:
            stats = table_stats(cur, table)
            if stats is None:
                reason = f"{table}: not found in pg_stat_user_tables -- is the table missing?"
                print(f"FAIL  {reason}")
                reasons.append(reason)
                failed = True
                continue

            autovac_off = any("autovacuum_enabled=off" in opt for opt in stats["reloptions"])
            if autovac_off:
                reason = f"{table}: autovacuum still disabled (reloptions={stats['reloptions']})"
                print(f"FAIL  {reason}")
                reasons.append(reason)
                failed = True
            else:
                shown = stats["reloptions"] or "none"
                print(f"PASS  {table}: autovacuum_enabled=off not present (reloptions={shown})")

            vacuumed = stats["last_vacuum"] is not None or stats["last_autovacuum"] is not None
            if not vacuumed:
                reason = f"{table}: never vacuumed (last_vacuum and last_autovacuum both NULL)"
                print(f"FAIL  {reason}")
                reasons.append(reason)
                failed = True
            else:
                when = stats["last_vacuum"] or stats["last_autovacuum"]
                print(f"PASS  {table}: vacuumed at least once (most recent: {when})")

            ratio = stats["n_dead"] / max(stats["n_live"], 1)
            if ratio >= MAX_DEAD_RATIO:
                reason = (
                    f"{table}: dead-tuple ratio {ratio:.4f} >= {MAX_DEAD_RATIO} "
                    f"(n_dead={stats['n_dead']}, n_live={stats['n_live']})"
                )
                print(f"FAIL  {reason}")
                reasons.append(reason)
                failed = True
            else:
                print(f"PASS  {table}: dead-tuple ratio {ratio:.4f} < {MAX_DEAD_RATIO}")

            print(
                f"info  {table}: total relation size {stats['total_size']}, "
                f"n_live={stats['n_live']}, n_dead={stats['n_dead']}"
            )

    conn.rollback()
    conn.close()

    # Informational only: not part of pass/fail. Only meaningful if a
    # covering index from task 04 already exists on orders.
    try:
        plan = get_plan(IOS_PROBE_SQL)
        ios_nodes = find_nodes(plan, "Index Only Scan", table="orders")
        if ios_nodes:
            for node in ios_nodes:
                print(
                    f"info  orders Index Only Scan Heap Fetches: {node.get('Heap Fetches')} "
                    f"(rows returned: {node.get('Actual Rows')})"
                )
        else:
            print(
                "info  no Index Only Scan reached on orders for the task-04-shaped query "
                "(task 04 not done on this DB, or no covering index present) -- skipping "
                "Heap Fetches report"
            )
    except psycopg.Error as e:
        print(f"info  could not probe the task-04-shaped query: {e}")

    if failed:
        print(f"NOT PASSED: {'; '.join(reasons)}")
        sys.exit(1)

    print("PASSED")
    sys.exit(0)


if __name__ == "__main__":
    main()
