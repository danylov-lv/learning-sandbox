# 06 -- SQL Injection (break-and-fix)

## Backstory

A "quick" product search endpoint went out under deadline pressure:
`GET /search?q=<text>` builds its SQL by dropping `q` straight into an
f-string. It works -- searches return real products -- and nobody noticed
anything wrong in review, because it *looks* fine for ordinary queries.
It isn't. A security scan just flagged it, and your job is to fix it before
it ships further: prove the hole is real, close it, and add a second layer
so a future regression like this one can't reach anything sensitive.

This task is shaped differently from the others in this module. `src/app.py`
is **not** a stub that raises `NotImplementedError` -- it is a complete,
running, *deliberately vulnerable* endpoint. You fix it in place. You are
not done when the endpoint "works"; the stock code already works. You are
done when it can no longer be exploited.

## What's given

- `src/app.py` -- a FastAPI `app` with a working `GET /search` route. The
  query is built by **string interpolation**:
  `f"SELECT id, title, price FROM shop.products WHERE title ILIKE '%{q}%' LIMIT 20"`.
  This is real, exploitable SQL injection, not a toy example -- see
  `tests/exploit.py`.
- `SEARCH_ROLE_NAME = "t06_search"` -- the name the fix's least-privilege
  role must use. The validator imports this constant.
- `tests/exploit.py` -- a standalone/importable script that fires a
  UNION-based injection payload at `/search` and reports whether it leaked
  a seeded user's real `email`/`password_hash`. Run it directly:
  `uv run python tests/exploit.py`. Against the stock code it prints
  `EXPLOIT SUCCEEDED: leaked <email>/<hash prefix>...` and exits 0.
- The shared, read-only `shop` corpus (`shop.products`, `shop.users`) and
  the module harness (`harness/common.py`, `harness/service.py`).
- This task owns Postgres schema `t06` (currently unused, reserved per the
  module's per-task namespacing convention) and Postgres roles named
  `t06_*` -- specifically the `t06_search` role you create as part of the
  fix.

## What's required

Fix `src/app.py` in place. Two layers, both required:

1. **Parametrization.** Rewrite the query so `q` is passed as a bound
   parameter (a psycopg `%s` placeholder), never interpolated into the SQL
   text. Do this correctly for an `ILIKE '%...%'` pattern -- the `%`
   wildcards are part of the SQL pattern, not part of the untrusted value,
   so think about where they belong once `q` is a parameter instead of
   embedded text.
2. **Least-privilege DB role (defense in depth).** Create a Postgres role
   named `t06_search` (see "Database setup" below) that can `SELECT` from
   `shop.products` and has **no access whatsoever** to `shop.users`.
   Reconnect the `/search` endpoint using that role's credentials instead
   of the shared admin DSN (`harness.common.pg_dsn()`). The idea: even if a
   future change reintroduces an injection, the DB connection itself has no
   path to credentials -- the vulnerability becomes unable to reach
   anything worth stealing.

Parametrization alone satisfies most of the graded checks. The role is
checked independently and separately -- do both.

## Database setup

Creating the role is infrastructure, not the exercise -- here is the exact
DDL. Run it once (`docker compose exec -T postgres psql -U sandbox -d
sandbox`, or a short psycopg script using `harness.common.pg_conn()`, which
connects as the `sandbox` superuser-equivalent DB owner and can `CREATE
ROLE`):

```sql
DROP ROLE IF EXISTS t06_search;
CREATE ROLE t06_search LOGIN PASSWORD 'pick-your-own-local-password';
GRANT CONNECT ON DATABASE sandbox TO t06_search;
GRANT USAGE ON SCHEMA shop TO t06_search;
GRANT SELECT ON shop.products TO t06_search;
-- A brand-new role already has zero privileges on shop.users by default;
-- this line just makes the intent explicit and survives someone later
-- granting shop-wide access by accident.
REVOKE ALL PRIVILEGES ON shop.users FROM t06_search;
```

Idempotent by construction (`DROP ROLE IF EXISTS` then `CREATE`), so rerunning
it is safe. Point `src/app.py`'s DB connection for `/search` at this role
instead of `pg_dsn()` -- you'll need your own connection string with
`user=t06_search` and the password you chose.

## Completion criteria

Run, from this task's directory:

```bash
uv run python tests/exploit.py     # against your FIXED app: EXPLOIT FAILED, exit 1
uv run python tests/validate.py
```

`validate.py` launches your app on an ephemeral port and checks, in order:

1. The exploit (same payload as `tests/exploit.py`) must **fail** -- if it
   still leaks `shop.users` data, `NOT PASSED: ... still injectable`.
2. A real search (`q=Power Bank`-style substring) still returns correct
   matches, checked row-by-row against `shop.products` directly -- the fix
   must not break search. A nonsense substring returns zero rows.
3. A benign-looking payload containing SQL metacharacters (a quote, `--`,
   `;`) is treated as a **literal** search string: HTTP 200 (never a 500),
   and `shop.products`' row count is unchanged.
4. The `t06_search` role exists, can read `shop.products`, and cannot read
   `shop.users` at all (checked directly via Postgres, independent of how
   your app connects).

Prints `PASSED: ...` or `NOT PASSED: <reason>` and exits 0/1.

## Estimated evenings

1

## Topics to read up on

- SQL injection: string interpolation vs. bound/parametrized queries
- Why `UNION SELECT` is the classic way to pivot an injection into an
  unrelated table
- Why manually escaping quotes (`q.replace("'", "''")`) is not a real fix
- psycopg3 parameter binding (`conn.execute(sql, params)`), and `ILIKE`
  pattern construction with a bound parameter
- Principle of least privilege for database roles; `GRANT`/`REVOKE`,
  `has_table_privilege`
- Defense in depth: why a role restriction still matters even after the
  "real" fix (parametrization) is in place

## Off-limits

`.authoring/design.md` (at the module root) holds the harness API contract,
the corpus ground truth, and the verification philosophy behind every task
in this module -- spoilers. Don't read it before finishing this task.
