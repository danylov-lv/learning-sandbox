"""Validator for 12-api-engineering task 06 -- SQL injection break-and-fix.

This is a SECURITY task, not a "fill in NotImplementedError" one: src/app.py
ships a WORKING but deliberately vulnerable /search endpoint. Verification
checks BOTH directions:

  1. The exploit (tests/exploit.py) must FAIL against the current app -- if
     it still leaks shop.users credentials, NOT PASSED immediately ("still
     injectable"), before any other check runs.
  2. Functional: /search must still return correct matches for a real title
     substring (the fix must not break search) -- checked per-row against
     shop.products directly (an independent oracle), so it does not depend
     on LIMIT/ordering matching some separately-issued query byte for byte.
     A nonsense substring must return zero rows (proves it's actually
     filtering, not just returning "the first N products" regardless of q).
  3. A benign-looking payload containing SQL metacharacters (quote, `--`,
     `;`) must be treated as a literal search string: HTTP 200, never a 500,
     and shop.products' row count must be unchanged (belt-and-suspenders
     against any accidental mutation).
  4. Least privilege: a Postgres role named SEARCH_ROLE_NAME (t06_search)
     must exist, have SELECT on shop.products, and have NO access to
     shop.users at all. This is checked directly via `has_table_privilege`
     against the shared Postgres, independent of how (or whether) the app
     itself connects as that role.

On the unmodified stock app, check 1 finds the leak and this validator
prints NOT PASSED. Run from this task's directory:

    uv run python tests/validate.py
"""

import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))
sys.path.insert(0, str(TASK_ROOT))

from harness.common import guarded, not_passed, passed, pg_conn, run_async  # noqa: E402
from harness.service import run_app  # noqa: E402

from src.app import SEARCH_ROLE_NAME, app  # noqa: E402
from tests.exploit import attempt_exploit  # noqa: E402

POSITIVE_QUERY = "Power Bank"  # a real, common product-title substring
NEGATIVE_QUERY = "zzzz_definitely_absent_token_9999"  # must match nothing


def _ensure_t06_schema():
    """t06 is this task's owned (currently unused) Postgres schema -- create
    it idempotently so the namespace exists per the module's convention,
    even though this task stores no tables in it."""
    with pg_conn() as conn:
        conn.execute("CREATE SCHEMA IF NOT EXISTS t06")
        conn.commit()


async def _check_functional_search(client, pg):
    resp = await client.get("/search", params={"q": POSITIVE_QUERY})
    if resp.status_code != 200:
        not_passed(
            f"GET /search?q={POSITIVE_QUERY!r} returned HTTP {resp.status_code}, expected 200 "
            f"(the fix must not break ordinary search)"
        )
    rows = resp.json()
    if not isinstance(rows, list) or len(rows) == 0:
        not_passed(f"GET /search?q={POSITIVE_QUERY!r} returned no rows -- expected real matches")

    for row in rows:
        title = str(row.get("title", ""))
        if POSITIVE_QUERY.lower() not in title.lower():
            not_passed(f"search result {row!r} does not contain {POSITIVE_QUERY!r} -- search is not filtering correctly")
        real = pg.execute(
            "SELECT title, price FROM shop.products WHERE id = %s", (row.get("id"),)
        ).fetchone()
        if real is None:
            not_passed(f"search returned id={row.get('id')!r} which does not exist in shop.products")
        if real[0] != title:
            not_passed(f"search returned id={row.get('id')} with title {title!r}, but shop.products has {real[0]!r}")
        try:
            price_ok = abs(float(real[1]) - float(row.get("price"))) < 0.01
        except (TypeError, ValueError):
            price_ok = False
        if not price_ok:
            not_passed(f"search returned id={row.get('id')} with price {row.get('price')!r}, but shop.products has {real[1]}")

    resp_neg = await client.get("/search", params={"q": NEGATIVE_QUERY})
    if resp_neg.status_code != 200:
        not_passed(f"GET /search?q={NEGATIVE_QUERY!r} returned HTTP {resp_neg.status_code}, expected 200")
    rows_neg = resp_neg.json()
    if rows_neg:
        not_passed(
            f"GET /search?q={NEGATIVE_QUERY!r} unexpectedly returned {len(rows_neg)} rows -- "
            f"search must actually filter by q, not ignore it"
        )
    return len(rows)


async def _check_benign_metacharacters(client, pg):
    # Deliberately harmless even if it somehow reached the DB as multiple
    # statements: no DDL/DML token anywhere in this payload, only a no-op
    # SELECT -- shop is shared, read-only, and must never be mutated.
    payload = "O'Brien\"s gadget -- ; SELECT 1"

    before = pg.execute("SELECT count(*) FROM shop.products").fetchone()[0]
    resp = await client.get("/search", params={"q": payload})
    after = pg.execute("SELECT count(*) FROM shop.products").fetchone()[0]

    if resp.status_code != 200:
        not_passed(
            f"benign payload {payload!r} (contains quotes/--/;) returned HTTP {resp.status_code} -- "
            f"a properly parametrized query treats it as a literal string, never a syntax error"
        )
    rows = resp.json()
    if not isinstance(rows, list):
        not_passed(f"benign payload {payload!r} did not return a JSON list: {rows!r}")
    for row in rows:
        title = str(row.get("title", ""))
        if payload.lower() not in title.lower():
            not_passed(
                f"benign payload {payload!r} produced a match {row!r} whose title does not literally "
                f"contain the payload -- looks like it was interpreted as SQL, not data"
            )
    if after != before:
        not_passed(
            f"shop.products row count changed ({before} -> {after}) after the benign-metacharacter "
            f"request -- the query must never mutate the shared schema"
        )


async def _run_async_checks():
    async with run_app(app) as svc:
        with pg_conn() as pg:
            async with svc.client(timeout=15.0) as client:
                leaked, detail = await attempt_exploit(client)
                if leaked:
                    not_passed(f"endpoint still injectable -- exploit succeeded: {detail}")

                matched = await _check_functional_search(client, pg)
                await _check_benign_metacharacters(client, pg)
    return detail, matched


def _check_least_privilege_role():
    with pg_conn() as conn:
        exists = conn.execute(
            "SELECT 1 FROM pg_roles WHERE rolname = %s", (SEARCH_ROLE_NAME,)
        ).fetchone()
        if not exists:
            not_passed(
                f"role {SEARCH_ROLE_NAME!r} does not exist yet -- create it as the least-privilege "
                f"defense-in-depth fix (see README's 'Database setup' section)"
            )
        can_read_products = conn.execute(
            "SELECT has_table_privilege(%s, 'shop.products', 'SELECT')", (SEARCH_ROLE_NAME,)
        ).fetchone()[0]
        can_read_users = conn.execute(
            "SELECT has_table_privilege(%s, 'shop.users', 'SELECT')", (SEARCH_ROLE_NAME,)
        ).fetchone()[0]
    if not can_read_products:
        not_passed(f"role {SEARCH_ROLE_NAME!r} cannot SELECT shop.products -- it must be usable for /search")
    if can_read_users:
        not_passed(f"role {SEARCH_ROLE_NAME!r} can still SELECT shop.users -- REVOKE that access (least privilege)")
    return f"role {SEARCH_ROLE_NAME}: SELECT on shop.products, no access to shop.users"


@guarded
def main():
    _ensure_t06_schema()

    exploit_detail, matched = run_async(_run_async_checks())
    role_detail = _check_least_privilege_role()

    passed(
        f"exploit blocked ({exploit_detail}); functional search returned {matched} correct rows; "
        f"benign metacharacters treated as literal; {role_detail}"
    )


if __name__ == "__main__":
    main()
