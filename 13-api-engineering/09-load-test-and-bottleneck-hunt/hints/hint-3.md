Concrete mechanics for each of the three things hint-2 pointed at, without
writing the handler for you. Fix and re-measure one at a time (`baseline.py`
or a plain `bombard()` call, either works informally) -- you should see the
numbers move after each individual change, not just after all three.

**Collapsing the extra round trips.** If you confirmed a query is being
issued once per row for data that's available via a foreign key already on
that row, the fix is a single `JOIN` in the ONE query that fetches the page,
pulling the related columns in as extra `SELECT`ed fields -- not a loop
issuing a second query. psycopg3's `conn.execute(sql, params).fetchall()`
returns tuples in column order, so a joined query just means more columns
per returned tuple, unpacked the same way. This fix touches only the SQL
text and the loop that turns rows into response dicts; it doesn't require
touching how the connection is obtained or how big the pool is.

**Getting a blocking call off the event loop.** Two honest options, and
either is fine: (a) wrap the blocking call in `starlette.concurrency.
run_in_threadpool(fn, *args)` (or the stdlib equivalent, `asyncio.to_thread
(fn, *args)`) and `await` that instead of calling the blocking function
directly -- this hands the actual blocking work to a worker thread and lets
the event loop keep servicing other requests while it waits; or (b) switch
to a genuinely async database client/pool (`psycopg`'s async connection
API, or an async pool) so the `await` at the call site is real, not
decorative. Whichever you choose, verify it actually helped: fire a
concurrent burst and watch p95 relative to p50 -- if the event loop was
really the problem, that gap should shrink noticeably, independent of
whatever the pool size or query count is doing.

**Sizing the pool.** Find where the pool is constructed and what
`min_size`/`max_size` it's given. A pool of size 1 means at most one
in-flight database operation for the ENTIRE process, no matter how much
concurrency the rest of the app can offer -- raising `max_size` to
something in the same ballpark as your expected concurrent request count
(not unbounded; an unbounded pool has its own failure modes under real
load, just not ones this task's load shape will expose) removes that
ceiling. This is a one-argument change; the interesting part is confirming
*with a load test*, not just by reading the number, that it was actually
constraining anything given whatever else you've already fixed.

**Confirming the response didn't change.** After each fix, a single
`curl`/`httpx` request against `/catalog/{category_id}` should still return
the exact same shape and values it did before you started -- if you're
unsure, compare it against the same JOIN query you used to fix the N+1
above; that query IS the correctness oracle `tests/validate.py` uses.
