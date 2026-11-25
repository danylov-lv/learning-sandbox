If `uv run python baseline.py` runs but `tests/validate.py` says the
process speedup on `cpu_bound` is too low, check these in order:

1. **Is `max_workers` actually being used?** If `run_processes` ignores the
   `max_workers` argument and lets the executor default kick in, that's
   usually fine (the default is `os.cpu_count()`), but if you hardcoded
   `max_workers=1` or forgot to pass it through from the function
   signature into the `ProcessPoolExecutor(...)` call, you've built a pool
   that can't parallelize anything.
2. **Is the pool actually blocking until every result is back?** If
   `run_processes` submits the work but returns before collecting every
   `.result()` (or before the `with` block exits), you're timing "how long
   it took to submit the work," not "how long the work took" -- this
   usually shows up as a suspiciously *fast* number rather than a slow one.
3. **Is `CPU_N` too small relative to process-startup overhead?** On some
   machines, spawning a process pool has a fixed cost (interpreter
   startup, re-importing modules) that's large relative to a very short
   `cpu_bound` call. This task's shipped `CPU_N` in `workloads.py` was
   tuned to keep a single call comfortably longer than that overhead --
   you shouldn't need to touch it, but if your particular machine is
   unusually slow to spawn processes, that's the constant to look at
   (don't touch `workloads.py` itself; if you suspect this, say so in
   `NOTES.md` rather than silently editing the provided file).

If instead the *thread* speedup on `cpu_bound` is suspiciously high (close
to or above `MAX_THREAD_SPEEDUP`), check whether `run_threads` is somehow
routing work through something that releases the GIL that it shouldn't be
-- for instance, if you changed `run_threads` to call a different function
than the one it was actually asked to run, or if you're timing something
other than the full batch's completion.

If the `io_bound` speedups look too low, the most common cause is
accidentally awaiting each call one at a time (`for a in awaitables: await
a`) instead of concurrently (`await asyncio.gather(*awaitables)`) inside
`run_asyncio`, or passing `max_workers=1` to the `ThreadPoolExecutor` in
`run_threads`.
