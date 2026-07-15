The bottleneck is the database layer, not the HTTP layer -- and that's the
part most people skip past because `StreamingResponse` looks like the
"streaming API" and the DB call looks like plumbing.

`StreamingResponse` is honest about what it does: it takes anything
iterable (or async-iterable) and writes each item to the client as it comes
out of the iterator, using chunked transfer encoding. It has no way to know
whether the iterator you handed it is actually lazy or whether it's a
`list` in disguise that already did all its work before you called `iter()`
on it. A `for row in [200000 rows already in memory]: yield ...` generator
satisfies `StreamingResponse`'s interface perfectly and buys you nothing --
the response writer streaming the OUTPUT doesn't undo the driver having
already materialized the INPUT.

So the fix lives entirely on the Postgres side. A plain
`cur.execute(...)` followed by `cur.fetchall()` (or even implicit
`fetchall()`-like behavior from iterating a default client-side cursor)
pulls the *entire* result set across the wire before your code sees the
first row. psycopg (and most Postgres drivers) offer a different mode:
a **server-side ("named") cursor** -- `conn.cursor(name="something")` in
psycopg3 -- which tells Postgres to hold the cursor open server-side and
only send rows across the wire as you actually ask for them, in batches. The
alternative that gets you the same property without a named cursor is
manually paging the query yourself: a `WHERE id > :last_id ORDER BY id
LIMIT :batch_size` loop, i.e. reusing the keyset-pagination idea from task
01, driven from inside the generator instead of from the client.

Either way, the shape you're building toward is: a bounded batch pulled
from Postgres -> that batch's rows fed one at a time into a generator's
`yield` -> that generator handed to `StreamingResponse`. All three links
have to be lazy for the chain to actually behave the way the docstring
promises. The next hint gets concrete about the batching loop, cursor
lifetime, and the JSON-serialization gotchas (`Decimal`, `datetime`) you'll
hit the moment you stop trusting `fetchall()`'s implicit conversions.
