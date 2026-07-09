"""Checker for 09-deep-pagination.

Run from the module root:
    uv run python 09-deep-pagination/tests/check.py

Verifies, in order:
  1. The learner's src/page_query.sql, given the cursor of the row just
     before the deep page, returns exactly the same 100 rows (same order)
     as the given OFFSET query's deep page.
  2. Walking 3 consecutive pages via repeated cursor application matches
     the corresponding OFFSET pages row-for-row (catches unstable sort /
     tie-break bugs).
  3. The keyset page is at least MIN_SPEEDUP times faster than the OFFSET
     deep page, timed against a machine-local baseline recorded from
     src/given_query.sql.
  4. The learner query's plan contains an Index Scan-family node on
     inventory_events whose Actual Rows is small -- proof there is no
     offset-walking happening under the hood.
"""

import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

import psycopg  # noqa: E402
from psycopg import sql as pgsql  # noqa: E402

import baseline  # noqa: E402
from plan_check import (  # noqa: E402
    PlanAssertionError,
    conninfo,
    find_nodes,
    get_plan,
)

TASK_DIR = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_DIR.parent
GIVEN_QUERY_FILE = TASK_DIR / "src" / "given_query.sql"
PAGE_QUERY_FILE = TASK_DIR / "src" / "page_query.sql"
BASELINE_FILE = MODULE_ROOT / "baseline-local.json"

QUERY_ID = "given_query_09"
OFFSET_DEEP = 800000
PAGE_SIZE = 100
MIN_SPEEDUP = 30.0
MAX_INDEX_SCAN_ACTUAL_ROWS = 1000


def offset_page(cur, offset, limit):
    cur.execute(
        """
        SELECT id, product_id, event_type, qty_delta, occurred_at
        FROM inventory_events
        ORDER BY occurred_at DESC, id DESC
        OFFSET %s LIMIT %s
        """,
        (offset, limit),
    )
    return cur.fetchall()


def cursor_before(cur, offset):
    """Return (occurred_at, id) of the row immediately preceding `offset`
    (0-indexed) in the ORDER BY occurred_at DESC, id DESC sequence -- i.e.
    the last row of the page ending at `offset`."""
    rows = offset_page(cur, offset - 1, 1)
    if not rows:
        raise RuntimeError(f"no row at offset {offset - 1}")
    row = rows[0]
    return row[4], row[0]  # occurred_at, id


def run_page_query(cur, page_sql, cursor_occurred_at, cursor_id):
    cur.execute(
        page_sql,
        {"cursor_occurred_at": cursor_occurred_at, "cursor_id": cursor_id},
    )
    return cur.fetchall()


def literal_sql(conn, page_sql, cursor_occurred_at, cursor_id):
    """Substitute the named placeholders with SQL literals so the query
    becomes a plain, param-free string usable with plan_check.get_plan
    and baseline.time_query, neither of which take bind parameters."""
    ts_literal = pgsql.Literal(cursor_occurred_at).as_string(conn)
    id_literal = pgsql.Literal(cursor_id).as_string(conn)
    return page_sql.replace("%(cursor_occurred_at)s", ts_literal).replace(
        "%(cursor_id)s", id_literal
    )


def fail(reason):
    print(f"FAIL  {reason}")
    print(f"NOT PASSED: {reason}")
    sys.exit(1)


def main():
    if not PAGE_QUERY_FILE.exists():
        fail(f"missing {PAGE_QUERY_FILE}")

    page_sql = PAGE_QUERY_FILE.read_text(encoding="utf-8")
    given_sql = GIVEN_QUERY_FILE.read_text(encoding="utf-8")

    try:
        conn = psycopg.connect(conninfo())
    except psycopg.Error as e:
        print(f"NOT PASSED: could not connect: {e}")
        sys.exit(1)

    try:
        with conn.cursor() as cur:
            # --- 1. single deep page matches exactly -----------------------
            cursor_occurred_at, cursor_id = cursor_before(cur, OFFSET_DEEP)
            reference_page = offset_page(cur, OFFSET_DEEP, PAGE_SIZE)

            try:
                learner_page = run_page_query(cur, page_sql, cursor_occurred_at, cursor_id)
            except psycopg.Error as e:
                conn.rollback()
                fail(f"page_query.sql failed to execute with the supplied cursor params: {e}")

            if learner_page != reference_page:
                fail(
                    f"page_query.sql returned {len(learner_page)} rows that do not match "
                    f"the reference deep page row-for-row (expected {len(reference_page)} rows "
                    "identical in content and order to the OFFSET query's page)"
                )
            print("PASS  keyset page matches the OFFSET deep page exactly")

            # --- 2. walk 3 consecutive pages --------------------------------
            for k in range(3):
                off = OFFSET_DEEP + k * PAGE_SIZE
                c_at, c_id = cursor_before(cur, off)
                ref = offset_page(cur, off, PAGE_SIZE)
                try:
                    got = run_page_query(cur, page_sql, c_at, c_id)
                except psycopg.Error as e:
                    fail(f"page_query.sql failed on page {k + 1} of the walk: {e}")
                if got != ref:
                    fail(
                        f"page {k + 1} of the 3-page walk does not match the corresponding "
                        "OFFSET page -- check the tie-break ordering on (occurred_at, id)"
                    )
            print("PASS  3-page cursor walk matches the corresponding OFFSET pages")

        conn.rollback()
    finally:
        conn.close()

    # --- 3. timing -------------------------------------------------------
    if not BASELINE_FILE.exists() or QUERY_ID not in baseline.load_baseline(BASELINE_FILE):
        fail(
            "record the baseline first: uv run python tools/baseline.py record "
            f"09-deep-pagination/src/given_query.sql --id {QUERY_ID}"
        )

    data = baseline.load_baseline(BASELINE_FILE)
    base_ms = data[QUERY_ID]["median_ms"]

    with psycopg.connect(conninfo()) as conn2:
        literal_page_sql = literal_sql(conn2, page_sql, cursor_occurred_at, cursor_id)

    try:
        timings = baseline.time_query(literal_page_sql, runs=5, warmups=1)
    except psycopg.Error as e:
        fail(f"timing run of page_query.sql failed: {e}")

    median = statistics.median(timings)
    speedup = base_ms / median if median > 0 else float("inf")
    if speedup >= MIN_SPEEDUP:
        print(
            f"PASS  {median:.2f} ms vs baseline {base_ms:.2f} ms -> "
            f"{speedup:.1f}x speedup (required >= {MIN_SPEEDUP}x)"
        )
    else:
        fail(
            f"{median:.2f} ms vs baseline {base_ms:.2f} ms -> only {speedup:.1f}x speedup "
            f"(required >= {MIN_SPEEDUP}x)"
        )

    # --- 4. structural: index-driven, not offset-walking ------------------
    try:
        plan = get_plan(literal_page_sql)
    except psycopg.Error as e:
        fail(f"could not obtain plan for page_query.sql: {e}")

    hits = find_nodes(plan, "Index Scan", table="inventory_events", family=True)
    if not hits:
        fail(
            "no Index Scan-family node on inventory_events found in the keyset query's "
            "plan -- the rewrite must be reachable via an index, not a scan of the table"
        )

    worst_rows = max(h.get("Actual Rows", 0) * max(h.get("Actual Loops", 1), 1) for h in hits)
    if worst_rows > MAX_INDEX_SCAN_ACTUAL_ROWS:
        fail(
            f"Index Scan node(s) on inventory_events report {worst_rows} actual rows, "
            f"above the {MAX_INDEX_SCAN_ACTUAL_ROWS}-row ceiling -- this looks like the "
            "index is still being walked from the start rather than seeked to the cursor"
        )
    print(
        f"PASS  Index Scan on inventory_events touches only {worst_rows} rows "
        f"(<= {MAX_INDEX_SCAN_ACTUAL_ROWS}) -- no offset-walking"
    )

    print("PASSED")
    sys.exit(0)


if __name__ == "__main__":
    main()
