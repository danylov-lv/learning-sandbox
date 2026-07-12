A concrete shape, without writing the Python for you:

1. Create `queue = asyncio.Queue(maxsize=max_in_flight)` and a mutable place
   to accumulate the checksum (a `list[int]` of length 1, or a small class --
   anything a closure can mutate, since a plain `int` in an enclosing scope
   can't be reassigned from a nested coroutine without `nonlocal`).

2. Write a producer coroutine: loop `i` from `0` to `produce_n - 1`, build
   the item (index + `PAYLOAD_SIZE` payload, per the docstring), `await
   queue.put(item)`. That's it for the loop body -- the `put()` is what
   blocks when the queue is full, nothing else needed. After the loop, the
   producer must signal "done" to the consumer side (see step 4).

3. Write one or more consumer coroutines: loop forever, `item = await
   queue.get()`, check whether it's the shutdown signal from step 4 and
   break if so, otherwise `await consume_fn(item)`, add the item's index to
   the checksum accumulator, increment a consumed counter. One consumer
   task is enough to satisfy the contract; multiple consumer tasks pulling
   from the same queue also works and doesn't change the checksum logic
   (sum is order-independent, which is exactly why the contract specifies
   sum rather than a list).

4. Shutdown signal: two common approaches, either is fine --
   - **Sentinel value**: define a unique object (e.g. a module-level
     `_SENTINEL = object()`), have the producer `put()` one sentinel per
     consumer task after its loop ends, have each consumer `break` when it
     gets one. Simple, and pairs naturally with running producer and
     consumer(s) inside a `TaskGroup` (task 02) so `run_pipeline` doesn't
     return until everyone has finished -- which also gets you the "no
     leaked tasks" guarantee for free.
   - **`task_done()` / `join()`**: consumers call `queue.task_done()` after
     finishing each item (not the sentinel); `run_pipeline` does `await
     queue.join()` after the producer finishes, which waits until every
     `put()`ed item has had a matching `task_done()`. Then explicitly
     cancel the (now-idle, still-looping) consumer task(s) and await them
     before returning, since `join()` alone doesn't stop their `get()`
     loop.

5. Whichever approach, `run_pipeline` should not `return` until: the
   producer has finished, every item has been consumed, and every task it
   spawned is either completed or has been cancelled-and-awaited. That's
   what a leak-free "clean shutdown" means here.

One item's in-flight window should run from `put()` succeeding to `get()`
returning it to a consumer *about to process it* -- not to when
`consume_fn` finishes -- which is naturally what a `put()`/`get()` pair
already gives you, since the queue's occupancy count drops the instant
`get()` removes the item, regardless of how long `consume_fn` then takes.
