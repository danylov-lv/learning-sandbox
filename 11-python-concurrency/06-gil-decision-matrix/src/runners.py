"""t06 -- GIL decision matrix: run a batch of the SAME workload N different
ways and report how long each way took.

`src/workloads.py` gives you two module-top-level, picklable workload
functions: `cpu_bound(n)` (pure-Python, GIL-bound the whole time it runs)
and `io_bound(delay)` (a `time.sleep()`, GIL-released the whole time it
runs). Implement the four runners below so `baseline.py` can benchmark both
workloads across `sequential` / `threads` / `processes` (and `asyncio` for
the I/O case) on your own machine -- no numbers are given to you up front;
you measure them.

Every runner takes the SAME shape of arguments: a `workload` callable and
`args_list`, a list of argument tuples -- one tuple per call, each tuple
unpacked as `workload(*args)`. This lets one runner implementation handle
both `cpu_bound` and `io_bound` batches without caring which workload it's
driving.
"""

import time


def run_sequential(workload, args_list: list[tuple]) -> float:
    """Call `workload(*args)` once per entry in `args_list`, one at a time,
    in the calling thread/process -- no concurrency at all. This is the
    baseline every other runner is compared against.

    Args:
        workload: a callable, `workload(*args) -> Any`.
        args_list: a list of argument tuples, one per call. `len(args_list)`
            calls are made in total, in order.

    Returns:
        Total wall-clock elapsed seconds for all calls, via
        `time.perf_counter()` (or `harness.common.time_it`, your choice).
        The individual return values of `workload` are not needed by
        callers of this function -- only the elapsed time.
    """
    raise NotImplementedError


def run_threads(workload, args_list: list[tuple], max_workers: int | None = None) -> float:
    """Run the same batch as `run_sequential`, but fan the calls out across
    a `concurrent.futures.ThreadPoolExecutor` and wait for all of them to
    finish before returning.

    For `cpu_bound`, expect this to NOT be meaningfully faster than
    `run_sequential` -- pure-Python bytecode execution holds the GIL, so
    N threads running `cpu_bound` mostly take turns rather than running in
    parallel; you may even see it come out slightly slower than sequential
    once thread-switching overhead is added in. For `io_bound`, expect a
    large speedup -- `time.sleep()` releases the GIL, so the threads really
    do overlap while parked.

    Args:
        workload: a callable, `workload(*args) -> Any`.
        args_list: a list of argument tuples, one per call.
        max_workers: passed through to `ThreadPoolExecutor`; `None` lets the
            executor pick its own default. `baseline.py` calls this with an
            explicit value sized to the batch -- don't hardcode one here.

    Returns:
        Total wall-clock elapsed seconds for the whole batch to complete
        (pool creation + all calls + waiting for every result), via
        `time.perf_counter()`.
    """
    raise NotImplementedError


def run_processes(workload, args_list: list[tuple], max_workers: int | None = None) -> float:
    """Run the same batch as `run_sequential`, but fan the calls out across
    a `concurrent.futures.ProcessPoolExecutor` and wait for all of them to
    finish before returning.

    Each worker process has its own interpreter and its own GIL, so
    `cpu_bound` calls genuinely run in parallel across cores here -- this is
    the one strategy that should show a real speedup for CPU-bound
    pure-Python work. The cost: `workload` and each argument tuple must be
    picklable (true for both functions in `workloads.py`, since they're
    module-top-level), and every call pays process-startup and
    pickling/unpickling overhead that threads don't -- for cheap workloads
    that overhead can eat the entire speedup, or worse.

    Windows gotcha: `ProcessPoolExecutor` on Windows uses the `spawn` start
    method, which re-imports the calling module in each child process. Any
    code that CREATES a process pool must be guarded by
    `if __name__ == "__main__":` in the top-level script that calls it
    (that's `baseline.py`'s job, not this function's) -- otherwise spawning
    a child re-runs the whole script recursively. This function itself just
    needs `workload` to stay a plain top-level, picklable callable.

    Args:
        workload: a callable, `workload(*args) -> Any`. Must be picklable.
        args_list: a list of argument tuples, one per call. Each tuple must
            be picklable.
        max_workers: passed through to `ProcessPoolExecutor`; `None` lets
            the executor pick its own default (usually `os.cpu_count()`).

    Returns:
        Total wall-clock elapsed seconds for the whole batch to complete
        (pool creation + all calls + waiting for every result), via
        `time.perf_counter()`.
    """
    raise NotImplementedError


async def run_asyncio(workload, args_list: list[tuple]) -> float:
    """Run the same batch as `run_sequential`, but concurrently under
    asyncio, for the I/O-bound case only (`baseline.py` never calls this
    for `cpu_bound`).

    `workload` here is a plain blocking callable (`io_bound`, which calls
    `time.sleep()`) -- not a coroutine function. You have two documented,
    equally acceptable ways to drive it concurrently under asyncio; pick
    one, and say which one you picked in `NOTES.md`:

    1. Offload each blocking call to a thread via `asyncio.to_thread(
       workload, *args)` and `asyncio.gather(...)` the results -- this is
       the general pattern for "I already have a blocking call I can't
       rewrite" and is exactly what task 07 (sync/async bridging) covers in
       more depth.
    2. Since `io_bound`'s blocking work is *just* `time.sleep(delay)`,
       you could instead call `asyncio.sleep(delay)` directly for each
       entry (bypassing `workload` itself) and `asyncio.gather(...)` those.
       This sidesteps thread-pool overhead entirely but only works because
       you happen to know what's inside `io_bound` -- it wouldn't generalize
       to an arbitrary blocking callable the way option 1 does.

    Args:
        workload: a blocking callable, `workload(*args) -> Any`.
        args_list: a list of argument tuples, one per call.

    Returns:
        Total wall-clock elapsed seconds for the whole batch to complete,
        via `time.perf_counter()`. `baseline.py` calls this with
        `asyncio.run(run_asyncio(...))`.
    """
    raise NotImplementedError
