Start with `run_sequential` -- it's the easiest and it's also the number
every other runner is compared against, so get it right first.

```python
def run_sequential(workload, args_list):
    start = time.perf_counter()
    for args in args_list:
        workload(*args)
    return time.perf_counter() - start
```

Notice the shape: `args_list` is a list of tuples, and each tuple gets
unpacked with `*args` into the call. This is what lets one runner handle
both `cpu_bound(n)` (called as `cpu_bound(*( n, ))`) and `io_bound(delay)`
without knowing which one it's driving.

For `run_threads` and `run_processes`, both `concurrent.futures.
ThreadPoolExecutor` and `ProcessPoolExecutor` expose the same interface
(they share a common `Executor` base class), so the shape of both functions
ends up nearly identical -- only the class you instantiate differs. Look at
`Executor.submit()` (returns a `Future` you `.result()` later) and
`Executor.map()` (does the submit-and-wait-for-all in one call) -- either
works here, but think about which one makes it easier to unpack each
`args`-tuple correctly when `workload` takes more than one positional
argument (it doesn't, in this task, but the contract in `runners.py` says
it should handle any `args_list` of tuples -- don't hardcode "unpack
exactly one argument").

For `run_asyncio`, remember it's the only one of the four that's itself a
coroutine function (`async def`) -- `baseline.py` calls it via
`asyncio.run(run_asyncio(...))`, not directly. Time the whole batch the
same way as the others: `time.perf_counter()` before and after the
`asyncio.gather(...)` (or whatever concurrent-await construct you use).
