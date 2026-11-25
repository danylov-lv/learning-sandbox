"""s12.t06 -- SQL injection break-and-fix drill.

STOCK CODE IS DELIBERATELY VULNERABLE -- your job is to fix it in place; do
not delete this endpoint, secure it.

The story: `GET /search?q=<text>` is a public product-title search over the
shared, read-only `shop.products` table. As shipped, the SQL is built by
plain Python string interpolation -- textbook SQL injection. A UNION-based
payload in `q` can pivot off shop.products into shop.users and read
`email`/`password_hash` for a seeded user, which this endpoint must NEVER
expose. `tests/exploit.py` proves this live: it fires such a payload and
reports whether it leaked real credentials.

The fix has TWO required layers (README has the full contract; hints/ walks
through the reasoning without ready code):

  1. PARAMETRIZATION -- pass `q` as a bound parameter (a psycopg `%s`
     placeholder) instead of interpolating it into the SQL text. This alone
     turns any injection payload into a literal (almost always zero-match)
     search string.
  2. LEAST-PRIVILEGE DB ROLE -- defense in depth. Create a `t06_search`
     Postgres role with SELECT on shop.products ONLY (no grant on
     shop.users at all -- see README's "Database setup"), and connect this
     endpoint using that role's credentials instead of the shared admin
     DSN (`pg_dsn()`). Even a future/residual injection then physically
     cannot reach credentials, because the connection itself has no path
     to them.

Hand-escaping quotes yourself is NOT a fix -- see hints/hint-2.md for why.
"""

import psycopg
from fastapi import FastAPI

from harness.common import pg_dsn

# Expected name of the least-privilege role (fix layer 2). The validator
# imports this constant, so it and your role creation always agree on the
# name -- don't rename it without updating what you create in Postgres.
SEARCH_ROLE_NAME = "t06_search"

app = FastAPI(title="s12.t06 marketplace search (vulnerable -- fix me)")


@app.get("/search")
def search(q: str = ""):
    """Product title search -- VULNERABLE: `q` is interpolated straight into
    the SQL text, and the connection uses the shared admin DSN, so a UNION
    payload can pivot into shop.users. Fix both (see module docstring)."""
    sql = f"SELECT id, title, price FROM shop.products WHERE title ILIKE '%{q}%' LIMIT 20"
    with psycopg.connect(pg_dsn()) as conn:
        rows = conn.execute(sql).fetchall()
    return [{"id": r[0], "title": r[1], "price": float(r[2])} for r in rows]
