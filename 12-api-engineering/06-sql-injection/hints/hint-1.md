# Hint 1 -- direction

Look at how `sql` gets built in `src/app.py`:

```
sql = f"SELECT id, title, price FROM shop.products WHERE title ILIKE '%{q}%' LIMIT 20"
```

`q` comes straight from the query string, and it lands inside the SQL text
itself, between two single quotes. Nothing stops `q` from containing a
single quote of its own. The moment it does, `q` stops being "a value the
WHERE clause compares against" and starts being SQL that Postgres will
parse and execute -- because as far as the database is concerned, there is
no difference between "text the developer wrote" and "text the string
interpolation glued in a moment ago". The string is the query, by the time
`conn.execute(sql)` sees it.

Once you can close that quote early, you can append *anything* syntactically
valid: another clause, or a whole second `SELECT` joined with `UNION`. A
`UNION SELECT` doesn't need any relationship to `shop.products` at all --
Postgres will happily union in rows from a completely different table, as
long as the column count and (compatible) types line up with the original
query's three columns (`id`, `title`, `price`). That's the shape of the
exploit in `tests/exploit.py`: it doesn't touch `shop.products`'s real data
at all, it uses the `/search` endpoint as an unintended read window into
`shop.users` -- specifically `email` and `password_hash`, columns this
endpoint has no business ever returning.

Before reaching for a fix, make sure you can answer: why does the *shape*
of the query (three text/numeric-ish columns) determine what the attacker's
`UNION SELECT` has to look like? And why is `shop.users` reachable at all
from a search endpoint that never mentions it? (Hint for the second
question: what Postgres user is this connection running as, and what can
that user see?)
