"""t02 -- structured-concurrency fan-out with asyncio.TaskGroup.

The naive way to run a batch of coroutines concurrently and collect their
results is:

    tasks = [asyncio.create_task(worker(item)) for item in items]
    results = await asyncio.gather(*tasks)

This has no notion of a *scope* that owns the tasks it creates. If one
worker raises, asyncio.gather() (default return_exceptions=False) re-raises
that exception and returns control to the caller -- but the other tasks
created via create_task() were never told to stop. They keep running,
orphaned, with nothing left that will ever await, cancel, or observe them.
If a second one also fails later, that failure has no one listening for it;
Python logs "Task exception was never retrieved" to stderr and the caller
never learns about it. The first exception gather() happened to surface
looks like the whole story -- it isn't.

Implement run_fanout() using asyncio.TaskGroup (Python 3.11+) instead, so
that the function itself is the scope: nothing it starts can outlive it.
"""


async def run_fanout(items: list, worker) -> list:
    """Run `worker(item)` concurrently for every item in `items`, under
    structured concurrency, and return the results.

    Required guarantees:

    1. Full success: every `worker(item)` call runs concurrently (not
       serially), and the returned list holds one result per item, in the
       same order as `items` -- input order, not the order in which workers
       happened to finish. A worker that takes longer must not shift its
       result's position in the output.

    2. Single failure: the instant any one `worker(item)` raises, every
       other in-flight sibling call must be cancelled promptly. None may be
       left running to completion in the background, and none may be left
       orphaned (created but never awaited, cancelled, or otherwise
       resolved) after this function returns or raises.

    3. Propagation: the failure(s) must propagate to the caller of
       `run_fanout` -- not be swallowed, not be logged-and-dropped. Whether
       you let asyncio.TaskGroup's own ExceptionGroup/BaseExceptionGroup
       surface unchanged, or catch it and re-raise the single underlying
       exception, is an implementation choice; either is acceptable, but
       be consistent and note which one you built.

    4. No leaks, ever: whether this function returns normally or raises,
       every asyncio.Task it created must be finished by the time control
       returns to the caller. Nothing may still be alive and unresolved.

    Args:
        items: the batch to fan out over. Order matters for the return
            value (see guarantee 1) but items themselves are opaque to
            this function -- it only ever passes each one to `worker`.
        worker: an async callable, `worker(item) -> Any`. May raise.

    Returns:
        A list of results, one per item in `items`, in the same order as
        `items`.

    Raises:
        Whatever `worker` raised, if any call failed (see guarantee 3 for
        the exact shape you may choose to propagate).
    """
    raise NotImplementedError
