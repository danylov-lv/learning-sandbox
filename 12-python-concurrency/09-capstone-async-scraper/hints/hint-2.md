The connective tissue between the fetch side and the aggregate side is an
`asyncio.Queue(maxsize=queue_maxsize)`. A bounded queue's `put()` blocks
once the queue is full, and resumes on its own the instant the consumer
frees a slot with `get()` -- that block IS the backpressure; you don't
implement it, you get it for free from choosing a bounded queue over an
unbounded one or a plain list. (Task 04 built exactly this mechanism in
isolation; this is the same idea wired into a two-sided pipeline instead of
one producer and one consumer.)

Shape it as: some number of fetcher coroutines (each gated by the
semaphore from hint-1, each responsible for a subset of `paths` or pulling
paths off a shared work queue -- either is fine) that, on a successful
fetch, `await queue.put(record)`; and exactly one aggregator coroutine
that loops `await queue.get()`, folds the record into
count/price_sum/per_category_count, and repeats. Both sides need to run
CONCURRENTLY with each other, not sequentially -- if you fetch everything
first and only start the aggregator afterward, the queue never applies any
backpressure at all, because nothing is competing with the fetchers for
queue space while they run.

The tricky part is knowing when to stop: the aggregator has no way to know
"no more items are coming" except being told. A common, clean pattern is a
sentinel value put onto the queue once every fetcher has genuinely
finished (success or a raised, unretryable failure) -- but figure out
precisely when "every fetcher has finished" is true before reaching for
that, since getting it wrong either hangs the aggregator forever (nobody
ever puts the sentinel) or ends it early (a sentinel arrives while
fetchers are still running). `asyncio.TaskGroup` is a good fit for owning
the set of fetcher tasks: once the `async with asyncio.TaskGroup() as tg:`
block around your fetcher spawns exits normally, every fetcher is known to
be done, which is exactly the moment you know it's safe to signal the
aggregator to stop and then await its own result.

Watch what happens to the queue and the aggregator if a fetcher raises
(after exhausting its retries, in CP2) instead of finishing normally --
`TaskGroup` will cancel its siblings, but nothing cancels the aggregator
coroutine for you just because it isn't itself inside the group. Decide
where the aggregator lives (inside the same group as the fetchers, or
tracked separately) so that a raised exception still leaves nothing
running afterward -- this is exactly what CP1 and CP2's `leaked_tasks`
check is watching for.
