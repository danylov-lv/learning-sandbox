Three different classes of application-layer bottleneck tend to explain
"fast alone, collapses under concurrency" symptoms. All three are worth
checking for in this endpoint -- checking doesn't mean assuming, so verify
each one rather than taking this list as a diagnosis.

**How many round trips does ONE request actually make?** A response with a
handful of fields per item can still cost far more than one query to build,
if each item's extra fields (here: the seller's name/tier) are fetched with
their own follow-up query instead of being pulled in alongside the main one.
This is the classic "N+1" shape: 1 query for the page, plus N more, one per
row. It doesn't show up in the response at all -- only in how many round
trips Postgres actually saw. `SELECT count(*) FROM pg_stat_activity WHERE
datname = 'sandbox'` polled during a burst, or just literally counting how
many times your instrumented code path executes a query for a single
request, will tell you directly.

**Does the app's own process get to do anything else while a request is
being handled?** `async def` doesn't make a function non-blocking by
itself -- it only means the function *can* yield control back to the event
loop at `await` points. A synchronous, blocking call inside a coroutine (a
plain driver call that isn't wrapped for the thread pool, a `time.sleep`
instead of `asyncio.sleep`) does not yield anything; it occupies the one
thread the event loop runs on for its whole duration. Watch your app's CPU
usage (Task Manager / `docker stats` if it were containerized, or just
`time` around a burst) while a concurrent burst is running: does it look
like it's doing several things "at once," or does it look suspiciously
serial for something that's supposedly async?

**How much can actually happen inside the database at once?** However the
app talks to Postgres, it goes through some kind of connection handle. If
there's a pool involved, its size is a hard ceiling: however much
concurrency the rest of the app can offer, no more than that many things can
be talking to the database simultaneously. Find where the pool (or
connection) is created and what size it's configured with.

Investigate all three independently before you fix anything -- the point of
the next hint is that each of these, once confirmed, has its own small,
separate fix, and fixing one doesn't require touching the others.
