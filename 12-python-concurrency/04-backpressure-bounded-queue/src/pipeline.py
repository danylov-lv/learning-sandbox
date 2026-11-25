"""s11.t04 -- backpressure via a bounded queue.

A producer/consumer pipeline has two independently-paced halves: something
that creates work (fetch a page, read a row, generate an item) and something
that processes it (parse, write, upload) -- usually slower than production.
Wire them together with an UNBOUNDED buffer --

    buffer = []
    async def produce(n):
        for i in range(n):
            buffer.append(make_item(i))   # never waits for the consumer

-- and the producer has no way to know the consumer is falling behind. It
just keeps materializing items into memory as fast as it can, regardless of
how many are already waiting to be processed. Peak memory ends up
proportional to how many items were EVER produced, not to how much work is
genuinely in flight at any one instant -- a pipeline that would otherwise
run forever in bounded memory instead grows without bound and eventually
OOMs, purely because nothing ever told the producer to slow down. The same
failure shows up with `asyncio.Queue()` called with no `maxsize` -- an
"unbounded queue" is just a fancier unbounded list; `put()` never blocks.

Backpressure is the fix: give the buffer a maximum size, and make adding to
it BLOCK once that maximum is reached. The producer then only runs as fast
as the consumer drains the buffer -- exactly the flow-control behavior you
want from a pipeline meant to process an unbounded stream in bounded memory.
Note that a manual "if buffer is full: sleep a bit and check again" loop is
NOT the same thing -- it burns CPU polling and has no way to wake up exactly
when space frees; the mechanism you want blocks and resumes on its own.

This module defines the scaffold. Implement `run_pipeline` so that, however
large `produce_n` gets, peak memory during the run stays governed by
`max_in_flight`, not by `produce_n`.
"""

PAYLOAD_SIZE = 16 * 1024  # bytes per item -- large enough that item payloads
# dominate tracemalloc's traced peak over interpreter/task bookkeeping noise;
# the validator's bounded-memory check relies on this to get a clean signal.


async def run_pipeline(produce_n: int, consume_fn, max_in_flight: int) -> dict:
    """Run a bounded producer/consumer pipeline over `produce_n` items.

    Producer side:
        Generate items with indices `0, 1, ..., produce_n - 1`, IN ORDER.
        Each item must carry a payload of `PAYLOAD_SIZE` bytes -- e.g.
        `(i, bytearray(PAYLOAD_SIZE))` -- so its in-memory footprint is
        realistic instead of a bare int (a bare int wouldn't materialize the
        memory pressure this task is actually about).

    Consumer side:
        For each item, `await consume_fn(item)`. Treat `consume_fn` as slow
        and opaque -- you don't know or control how long it takes, only that
        it eventually completes. Its return value is not used for anything;
        what matters is that every item gets exactly one
        `await consume_fn(item)` call.

    The core constraint -- backpressure:
        At NO point during the run may more than `max_in_flight` items be
        "in flight" (produced but not yet fully consumed). This must be
        enforced by making the producer actually BLOCK when the buffer is
        full -- not approximated by a counter and a sleep loop. Something in
        the standard library already gives you exactly this blocking-when-
        full behavior; that's the mechanism to reach for (see hints if
        you're stuck on which one, and how to size it against
        `max_in_flight`).

    Shutdown:
        `run_pipeline` must not return until every item has been consumed
        and every task it started has either completed on its own or been
        cleanly awaited/cancelled -- nothing left running in the background
        after the function returns. A validator checks this with
        `harness.common.leaked_tasks`.

    Args:
        produce_n: number of items to produce, indices `0 .. produce_n - 1`.
        consume_fn: `async def consume_fn(item) -> Any` -- awaited once per
            item. May be slow. Return value is ignored.
        max_in_flight: the max number of items allowed to be produced-but-
            not-yet-consumed at any instant. Must be enforced structurally
            (a bounded buffer that blocks), not approximated.

    Returns:
        dict with:
            "consumed": total number of items consumed (must equal
                `produce_n` on success).
            "checksum": the sum of the indices of every consumed item --
                used by the validator to confirm every index contributed
                exactly once, regardless of which order concurrent
                consumers happen to finish in.
    """
    raise NotImplementedError
