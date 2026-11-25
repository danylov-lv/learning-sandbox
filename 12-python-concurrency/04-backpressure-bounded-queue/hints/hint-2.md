The primitive is `asyncio.Queue`, constructed with a `maxsize`:

```python
queue = asyncio.Queue(maxsize=max_in_flight)
```

Two of its methods are the entire mechanism, and both are coroutines you
`await`:

**`await queue.put(item)`** adds an item, but if the queue already holds
`maxsize` items, this call does not return until some other coroutine
removes one via `get()`. That's the block-not-poll behavior from hint-1,
built in -- no counter, no sleep loop, no race between checking and adding.
This is also *why* `maxsize` should be set to `max_in_flight` directly: the
number of items currently sitting in the queue (produced, not yet pulled
out and consumed) is exactly what "in flight" means here, so the queue's
own occupancy cap is the enforcement.

**`await queue.get()`** removes and returns the next item, but if the
queue is currently empty, this call does not return until something
`put()`s an item. Your consumer side wants this: a loop that keeps calling
`get()` and processing whatever comes back.

Note the asymmetry this creates: an item is "in flight" (counted against
`maxsize`) from the moment `put()` succeeds until `get()` removes it --
*not* until `consume_fn` finishes with it. If you want "in flight" to mean
"produced but not yet fully consumed" (matching the task's definition
precisely), think about whether a plain `get()`-then-process loop already
gives you that, or whether the moment of removal from the queue needs to
line up with the moment consumption starts, not finishes.

Left for hint-3: how the producer signals "no more items" to whatever is
running `get()` in a loop, and how `run_pipeline` waits for every item to
be fully drained before it returns (both needed for the "no leaked tasks,
clean shutdown" requirement).
