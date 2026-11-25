A concrete walk-through of the shape, without writing the Python for you.

**`process_batch`:**

1. Create one `asyncio.Semaphore(max_workers)` before you touch any items --
   a single shared semaphore instance, not one per item.
2. Define a small local async helper that takes one item and: acquires the
   semaphore (`async with sem:`), then `await`s `asyncio.to_thread(
   blocking_lib, item)` inside that block, and returns the result. The
   `async with` scope should cover only the actual offloaded call -- the
   semaphore is what limits how many `to_thread` calls are running at once,
   so releasing it (leaving the `async with` block) is what lets the next
   queued item's call start.
3. Build a list of these helper-coroutines, one per item, **in the same
   order as `items`** -- e.g. `[helper(item) for item in items]`. Building
   them doesn't start them running yet; they're coroutine objects, same as
   any other, until something awaits/schedules them.
4. Pass that whole list to `asyncio.gather(*that_list)` and `await` it. This
   is what actually starts all of them concurrently (up to the semaphore's
   limit) and collects their results back into a list matching the
   *original* order of the list you passed in -- which is the same order as
   `items`, because you built step 3 in that order. This is guarantee 3
   solved by construction, not by explicit sorting.
5. Return that list.

Check yourself against the three guarantees once this is in place: does
`blocking_lib` ever run anywhere except inside a `to_thread` call (guarantee
1)? Can more than `max_workers` of those `to_thread` calls be inside the
semaphore's critical section at once (guarantee 2, should be structurally
impossible given step 2)? Does `gather`'s result list line up with `items`
(guarantee 3, should follow from step 3+4)?

**`sync_entrypoint`:**

This one really is close to a single line: build the coroutine object by
calling `process_batch(items, blocking_lib, max_workers)`, then hand that
coroutine object to `asyncio.run(...)` and return what it gives back. Don't
`await` anything here -- `sync_entrypoint` is plain synchronous code, and
`await` is only legal inside `async def`. `asyncio.run` is the bridge that
lets a synchronous function still end up running that coroutine to
completion.
