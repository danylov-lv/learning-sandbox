# Hint 2 -- the fix, and why "escape the quotes" is a trap

The instinct a lot of people reach for first: "just escape the single
quotes in `q` before interpolating it" (double any `'` to `''`, or strip
quotes entirely). Resist this. It is not a fix, for a few reasons:

- You have to anticipate every metacharacter that matters to the SQL
  parser, in every context the value could end up in, forever. Quotes are
  the obvious one; you'll also find backslashes (depending on server
  settings), the way `ILIKE` treats `%`/`_` as pattern wildcards, encoding
  edge cases... The list is exactly as long as "everything a determined
  attacker can think of that you didn't," which is not a list you can ever
  finish.
- You are re-implementing, by hand, in application code, a job the
  database driver already does correctly: distinguishing "this is SQL
  syntax" from "this is a data value," at the wire-protocol level, not by
  string surgery.
- Even a "correct" hand-escaping scheme still means the untrusted value
  passes through a code path where it is, briefly, treated as SQL text
  that needs sanitizing. One missed case and you're back to square one.

The actual fix is to stop building the query as one interpolated string at
all. A **parametrized query** sends the SQL text and the value(s)
separately -- the SQL text is fixed (has placeholders), and the value is
handed to the driver/database as data, which by construction cannot be
interpreted as SQL syntax no matter what characters it contains. There is
no escaping step, because there is no step where the value is ever inside
the SQL text.

Look at how psycopg3's `conn.execute()` accepts a second argument. Then
think about `ILIKE '%{q}%'` specifically: once `q` is a bound parameter and
not embedded text, the `%` wildcard characters can't live in the SQL string
around `q` anymore the same way -- where do they need to move to for the
pattern to still mean "contains q anywhere"?

Once parametrization is done, the injection is closed -- a UNION payload
becomes a literal string nothing matches. But go one step further and ask:
*should this endpoint's DB connection be able to reach `shop.users` at
all, even in principle?* It shouldn't -- a product search has no reason to.
That's a second, independent layer: restrict what the connection itself is
*allowed* to see, so a completely different, unrelated future bug in this
endpoint (or a copy-pasted version of it elsewhere) still can't leak
credentials, because the credentials are outside what that DB role can
even read. This is "defense in depth" -- the second layer isn't there
because the first layer might fail on this exact bug, it's there because
you don't get to assume you've thought of every bug.
