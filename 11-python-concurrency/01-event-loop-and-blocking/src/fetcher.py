"""t01 -- rescue a fetcher that secretly starves the event loop.

The scraper you inherited looks async. It has `async def` on it, it
`await`s things, it even has a docstring bragging about "concurrent
fetching." Here is roughly what it does:

    async def fetch_all(base_url, paths, blocking_parse):
        results = {}
        async with aiohttp.ClientSession() as session:
            for path in paths:
                async with session.get(base_url + path) as resp:
                    body = await resp.read()
                results[path] = blocking_parse(body)
        return results

Two independent things are wrong with it, and either one alone is enough to
make the "concurrent" fetcher behave like a bottleneck a synchronous
`requests` loop would:

1. **The `for` loop `await`s one request, then the next, then the next.**
   Nothing about `async def` makes a plain `for` loop over sequential
   `await`s concurrent. Each `await session.get(...)` suspends THIS
   coroutine until that one response arrives, and only then does the loop
   move on to start the next request. With N paths and each request taking
   `latency` seconds, this takes roughly `N * latency` wall-clock time --
   exactly as serial as a blocking client, just with extra syntax. Nothing
   else was ever running concurrently with it, because nothing else was
   ever *started* until the previous `await` returned.

2. **`blocking_parse(body)` runs directly on the event loop thread.** Say
   the fetcher is fixed to issue all N requests concurrently (e.g. via
   `asyncio.gather`). The network waits now overlap -- but the moment each
   response arrives, this line runs:

       results[path] = blocking_parse(body)

   `blocking_parse` is a plain, synchronous, BLOCKING function -- it does
   real work for a few milliseconds (blocking I/O, or a native/C-extension
   parser such as `lxml`/`orjson` that releases the GIL while it runs),
   with no `await` inside it and no cooperative yield point during it.
   There is exactly one OS thread running your event loop. While that
   thread is inside `blocking_parse`,
   it is not polling sockets, not running other coroutines' callbacks, not
   servicing timers -- **nothing else in this process can make progress**,
   including a completely unrelated coroutine that just wants to
   `await asyncio.sleep(0.01)` to emit a heartbeat. `asyncio.sleep` and
   `time.sleep` look similar; they are opposites here. `asyncio.sleep`
   hands control back to the loop so other coroutines run while it waits.
   `time.sleep` -- and any other call that blocks the calling OS thread
   without yielding to the loop, `blocking_parse` included -- does the
   reverse: it holds the loop hostage for its entire duration. Do this once
   per response, N times, and you have re-introduced serialization through
   the back door, except now it looks concurrent in the code and isn't in
   practice.

The event loop is fundamentally single-threaded and cooperative: a
coroutine keeps running until it hits an `await` that actually yields
control (I/O wait, `asyncio.sleep`, waiting on another task/future). Any
uninterrupted stretch of synchronous work -- a blocking network call made
with a non-async library, `time.sleep`, a blocking file read, a tight CPU
loop -- freezes every other coroutine in the process for that stretch, no
matter how many `async def`s and `await`s surround it.

Your job: implement `fetch_all` so that (a) all paths are actually fetched
concurrently, and (b) the unavoidably-blocking `blocking_parse` step never
runs inline on the event loop thread -- it has to be offloaded somewhere
that lets the loop keep servicing other coroutines while it grinds.
"""


async def fetch_all(base_url: str, paths: list[str], blocking_parse) -> dict[str, object]:
    """Fetch every path in `paths` from `base_url` and parse each response
    body with `blocking_parse`, returning `{path: blocking_parse(body)}`.

    Args:
        base_url: the peer's base URL (e.g. `peer.base_url` from
            `harness.peer.mock_peer`). Join it with each path yourself
            (paths already start with "/").
        paths: the list of paths to fetch. May contain many entries --
            your implementation must not fetch them one at a time.
        blocking_parse: a SYNCHRONOUS, genuinely BLOCKING callable --
            blocking I/O, or a native/C-extension parser (e.g. `lxml`,
            `orjson`) that releases the GIL while it runs --
            `blocking_parse(body: bytes) -> object`. It is provided to you
            (you do not write it) and it is not `async` -- it cannot be
            `await`ed, and calling it takes real wall-clock time on
            whichever thread calls it, with no internal yield point. Treat
            it as a black box: you don't know or control how expensive it
            is, only that it is expensive enough to matter and that it
            blocks whatever thread runs it for the duration.

    Returns:
        A dict mapping every path in `paths` to `blocking_parse(body)`,
        where `body` is the raw response bytes fetched from
        `base_url + path`.

    Requirements this implementation must satisfy (see module docstring
    for why each one matters):

    1. All paths must be fetched CONCURRENTLY -- not via a `for` loop that
       `await`s one request before starting the next. The requests need to
       be in flight against the peer at the same time, not queued up
       behind each other.
    2. `blocking_parse` must NEVER be called directly on the coroutine that
       is running inside the event loop's thread. It must be handed off to
       something that runs it off that thread (or otherwise arranges for
       the loop to keep processing other work while it runs), then the
       result awaited back.
    3. The result dict must be complete and correctly keyed -- every path
       in `paths` appears exactly once, mapped to `blocking_parse` applied
       to THAT path's own response body (not some other path's).
    4. No dangling tasks left behind: whatever concurrency primitive you
       use, every task/future you create must be awaited (directly or via
       a gather/TaskGroup) before `fetch_all` returns -- don't fire a task
       with `asyncio.create_task` and let it go without ever awaiting it.

    You will need an `aiohttp.ClientSession` to talk to the peer, some
    mechanism for concurrent awaiting (see hints if you want a nudge on
    which one), and some mechanism for offloading a synchronous blocking
    call out of the event loop thread.
    """
    raise NotImplementedError
