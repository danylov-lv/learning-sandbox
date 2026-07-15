# Hint 3 -- concrete mechanics (still no ready code)

**Parametrizing the `ILIKE` search.** psycopg3's `conn.execute(sql, params)`
takes a SQL string with `%s` placeholders and a sequence of values -- the
driver sends them to Postgres separately, over the wire, as a genuine
parameterized statement (not string substitution on the client side). For
`title ILIKE '%<value>%'`, the `%` wildcard characters need to end up
*inside the parameter value itself* now, not in the SQL text around a
placeholder -- because the placeholder is a single opaque value slot, not a
text-splice point. So: build the actual pattern string (`"%" + q + "%"`)
in Python first, then pass *that whole pattern* as the one bound parameter
to a `WHERE title ILIKE %s` clause. Test it against a query containing a
literal `%` or `_` in `q` too, if you want to think about wildcard-escaping
as a follow-on (out of scope for this task's grading, but worth noticing).

**Creating and using the least-privilege role.** The DDL is in the README's
"Database setup" section verbatim -- that part isn't hidden, it's
boilerplate. What's on you: (a) actually running it once against the
Postgres instance (`docker compose exec -T postgres psql -U sandbox -d
sandbox`, or a one-off script using `harness.common.pg_conn()`, which
connects as the DB-owning `sandbox` user and can `CREATE ROLE`/`GRANT`);
(b) building a *second* DSN string for `/search`'s own connection that
authenticates as `t06_search` with the password you chose, instead of
reusing `harness.common.pg_dsn()` (which connects as the shared admin
user and can see everything, including `shop.users`); (c) wiring the
handler to actually use that second connection instead of the first one.

**Verifying the REVOKE actually took.** `has_table_privilege(role, table,
privilege)` is a plain SQL function you can run yourself: `SELECT
has_table_privilege('t06_search', 'shop.users', 'SELECT')` should come back
`false` once the role is set up correctly, and the same call against
`shop.products` should come back `true`. That's exactly what
`tests/validate.py` checks -- if you're not sure the role is right, run
that query by hand before running the validator.
