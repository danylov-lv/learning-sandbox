`run_threads` and `run_processes`, using the executor as a context manager
so it's always cleaned up:

```python
def run_threads(workload, args_list, max_workers=None):
    start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = [ex.submit(workload, *args) for args in args_list]
        for f in futures:
            f.result()  # wait for it, and re-raise if the call failed
    return time.perf_counter() - start
```

`run_processes` is the same shape with `ProcessPoolExecutor` instead of
`ThreadPoolExecutor` -- the `Executor` interface (`submit`, `.result()`,
context manager) is identical between the two classes. The behavioral
difference is entirely in what happens underneath: `ThreadPoolExecutor`
runs each call in a thread inside THIS process (same GIL, same memory);
`ProcessPoolExecutor` sends `workload` and each `args` tuple to a separate
worker process by pickling them, runs the call in a completely separate
interpreter (its own GIL), and pickles the result back.

Why `f.result()` in a loop and not `ex.map(workload, args_list)` directly?
Either works for the timing measurement in this task (both block until
everything is done), but `submit` + `result()` generalizes to argument
tuples of any length via `ex.submit(workload, *args)`, whereas `ex.map`
expects one iterable *per positional argument position*, which gets awkward
once you have to unpack tuples into separate parallel iterables. Either
choice is fine here since `workload` only ever takes one argument in this
task -- pick whichever reads cleaner to you.

For `run_asyncio`, decide between the two options in the `runners.py`
docstring (offload via `asyncio.to_thread`, or call `asyncio.sleep`
directly since you know `io_bound` is just a sleep) and write down which
one you picked in `NOTES.md`. Either way, the core shape is: build a list of
awaitables, `await asyncio.gather(*awaitables)`, time around it.
