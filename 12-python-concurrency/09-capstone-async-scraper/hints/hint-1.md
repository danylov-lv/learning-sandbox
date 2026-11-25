Start with the overall shape before worrying about chaos handling -- get
CP1 working first, against a peer that never fails a request, and only then
move on to hint-3's retry/timeout concerns for CP2.

The function has two jobs that want to run at different paces: FETCHING
(network-bound, benefits from concurrency, must never exceed
`max_concurrency`) and AGGREGATING (pure CPU, folding a fetched record's
`price` and `category` into a running total -- trivially fast here, but
treat it as if it weren't, because the shape has to generalize). Don't
write one flat loop that does both per item; split them into two
cooperating pieces from the start; hint-2 covers exactly how those two
pieces connect.

For the concurrency ceiling itself: `asyncio.Semaphore(max_concurrency)`,
acquired around the part of a fetch that actually talks to the peer
(`session.get(...)` and reading the response), released afterward
(`async with sem:` around that section handles both). Every fetch
coroutine you spawn goes through the same semaphore instance -- one shared
`Semaphore`, not one per coroutine. Remember the peer doesn't just prefer
you stay under the cap, it enforces it: cross it and you get HTTP 429 back
immediately (see `harness/peer.py`'s "Concurrency gate" if you want the
exact mechanics), and CP1's checks include `max_observed_concurrency <=
max_concurrency` as a hard pass/fail line, not a soft one.

One `aiohttp.ClientSession` for the whole `scrape()` call, opened with
`async with`, reused across every fetch -- not one session per request.
Sessions hold a connection pool; creating and tearing one down per request
throws that away and is both slower and a good way to eventually trip
something resource-related under load.
