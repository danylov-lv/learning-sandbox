"""Verify monthly partitioning against a snapshot of the original heap."""

import argparse
import hashlib
import json
import re
import statistics
import sys
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

import psycopg  # noqa: E402

import baseline  # noqa: E402
from plan_check import conninfo, get_plan, iter_nodes  # noqa: E402

TASK_ROOT = Path(__file__).resolve().parents[1]
BASELINE_FILE = TASK_ROOT.parent / "baseline-local.json"
SNAPSHOT_FILE = TASK_ROOT / "inventory-events-stock-local.json"
RECORD_STOCK_COMMAND = "uv run python 10-partition-the-firehose/tests/check.py --record-stock"
RECENT_WINDOW_QUERY_ID = "recent_window_stock"
RECENT_WINDOW_SQL = (
    "SELECT count(*) FROM inventory_events "
    "WHERE occurred_at >= now() - interval '14 days' AND occurred_at <= now()"
)
MAX_SCANNED_PARTITIONS = 2


class CheckError(ValueError):
    pass


def inventory_snapshot(cur):
    cur.execute("SELECT count(*), min(occurred_at), max(occurred_at) FROM inventory_events")
    rows, first, last = cur.fetchone()
    if rows == 0:
        raise CheckError("inventory_events is empty")
    if first is None or last is None:
        raise CheckError("inventory_events has no non-null event timestamps")

    digest = hashlib.sha256()
    with cur.copy(
        """
        COPY (
            SELECT id, product_id, event_type, qty_delta, occurred_at
            FROM inventory_events
            ORDER BY id, product_id, event_type COLLATE "C", qty_delta, occurred_at
        ) TO STDOUT (FORMAT CSV)
        """
    ) as copy:
        for row in copy:
            digest.update(row)

    return {
        "rows": rows,
        "first": first.isoformat(),
        "last": last.isoformat(),
        "sha256": digest.hexdigest(),
    }


def next_month(month):
    if month.month == 12:
        return month.replace(year=month.year + 1, month=1)
    return month.replace(month=month.month + 1)


def month_start(value):
    return value.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def check_months(cur, first, last):
    cur.execute(
        """
        SELECT pg_get_expr(child.relpartbound, child.oid)
        FROM pg_inherits
        JOIN pg_class child ON child.oid = inhrelid
        WHERE inhparent = 'inventory_events'::regclass
        """
    )
    monthly_starts = set()
    for (bounds,) in cur.fetchall():
        match = re.fullmatch(r"FOR VALUES FROM \('([^']+)'\) TO \('([^']+)'\)", bounds)
        if match:
            start, end = (datetime.fromisoformat(stamp) for stamp in match.groups())
            if start == month_start(start) and end == next_month(start):
                monthly_starts.add(start)

    month = month_start(first)
    future_month = next_month(month_start(last))
    missing = []
    while month <= future_month:
        if month not in monthly_starts:
            missing.append(month.strftime("%Y-%m"))
        month = next_month(month)
    if missing:
        raise CheckError(f"missing calendar-month partitions: {', '.join(missing)}")
    print("PASS  monthly partitions cover the source range and the next month")


def relation_state(cur):
    cur.execute(
        """
        SELECT relkind, relispartition, pg_get_partkeydef(oid)
        FROM pg_class
        WHERE oid = to_regclass('inventory_events')
        """
    )
    row = cur.fetchone()
    if row is None:
        raise CheckError("inventory_events is missing")
    return row


def capture_stock(cur):
    kind, is_partition, _ = relation_state(cur)
    if kind != "r" or is_partition:
        raise CheckError("--record-stock requires the original unpartitioned inventory_events")
    stock = inventory_snapshot(cur)
    with TemporaryDirectory(dir=SNAPSHOT_FILE.parent) as directory:
        temporary = Path(directory) / SNAPSHOT_FILE.name
        temporary.write_text(json.dumps(stock, indent=2) + "\n", encoding="utf-8")
        temporary.replace(SNAPSHOT_FILE)
    print(f"PASS  source snapshot recorded in {SNAPSHOT_FILE.name}")


def check_migration(cur):
    kind, _, key = relation_state(cur)
    if kind != "p" or key != "RANGE (occurred_at)":
        raise CheckError("inventory_events must be partitioned by RANGE (occurred_at)")
    print("PASS  inventory_events is RANGE-partitioned by occurred_at")

    if not SNAPSHOT_FILE.exists():
        raise CheckError(f"source snapshot is missing; run {RECORD_STOCK_COMMAND} on the original table")
    try:
        stock = json.loads(SNAPSHOT_FILE.read_text(encoding="utf-8"))
        first = datetime.fromisoformat(stock["first"])
        last = datetime.fromisoformat(stock["last"])
    except (KeyError, TypeError, ValueError) as e:
        raise CheckError(f"invalid source snapshot: {e}") from e

    check_months(cur, first, last)
    actual = inventory_snapshot(cur)
    if actual != stock:
        raise CheckError("the migrated event rows differ from the original table's saved snapshot")
    print(f"PASS  all {actual['rows']:,} event rows match the source snapshot")


def check_pruning(sql):
    plan = get_plan(sql)
    scanned = {
        node["Relation Name"]
        for node in iter_nodes(plan)
        if node.get("Relation Name") and node.get("Actual Loops", 0) > 0
    }
    if len(scanned) > MAX_SCANNED_PARTITIONS:
        raise CheckError(
            f"last-14-days query scanned {len(scanned)} partitions "
            f"(maximum {MAX_SCANNED_PARTITIONS}): {', '.join(sorted(scanned))}"
        )
    print(f"PASS  last-14-days query scanned {len(scanned)} partition(s)")


def report_timing(sql):
    try:
        data = baseline.load_baseline(BASELINE_FILE)
        if RECENT_WINDOW_QUERY_ID not in data:
            print("info  no stock timing baseline recorded")
            return

        stock_median = data[RECENT_WINDOW_QUERY_ID]["median_ms"]
        median = statistics.median(baseline.time_query(sql))
        speedup = stock_median / median if median > 0 else float("inf")
        print(f"info  recent-window query: {median:.1f} ms vs stock {stock_median:.1f} ms ({speedup:.2f}x)")
    except (KeyError, OSError, TypeError, ValueError, psycopg.Error) as e:
        print(f"info  could not compare recent-window timings: {e}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record-stock", action="store_true", help="snapshot the original heap before migration")
    args = parser.parse_args()

    try:
        with psycopg.connect(conninfo()) as conn, conn.cursor() as cur:
            cur.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            cur.execute("LOCK TABLE ONLY inventory_events IN ACCESS SHARE MODE")
            cur.execute("SET LOCAL DateStyle TO 'ISO, YMD'")
            if args.record_stock:
                capture_stock(cur)
            else:
                check_migration(cur)
        if not args.record_stock:
            check_pruning(RECENT_WINDOW_SQL)
            report_timing(RECENT_WINDOW_SQL)
    except (CheckError, OSError, psycopg.Error) as e:
        print(f"NOT PASSED: {e}")
        sys.exit(1)

    print("PASSED")


if __name__ == "__main__":
    main()
