"""Benchmark cpu_bound and io_bound across sequential/threads/processes
(and asyncio for I/O) on THIS machine, and write the results to a
gitignored `baseline-local.json` via `harness.common.write_baseline`.

Run this AFTER implementing `src/runners.py`:

    uv run python baseline.py

Then verify with:

    uv run python tests/validate.py

Windows gotcha: `run_processes` creates a `ProcessPoolExecutor`, which on
Windows uses the `spawn` start method -- each child process re-imports this
module from scratch. Without the `if __name__ == "__main__":` guard below,
importing this file in a child process would re-run the whole benchmark
recursively, spawning children that spawn children. The guard is required,
not stylistic, on this platform.
"""

import asyncio
import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parent
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))
sys.path.insert(0, str(TASK_ROOT))

from harness.common import write_baseline  # noqa: E402
from src.runners import run_asyncio, run_processes, run_sequential, run_threads  # noqa: E402
from src.workloads import BATCH_SIZE, CPU_N, IO_DELAY, cpu_bound, io_bound  # noqa: E402


def main():
    cpu_args = [(CPU_N,)] * BATCH_SIZE
    io_args = [(IO_DELAY,)] * BATCH_SIZE

    print(f"cpu_bound: n={CPU_N}, batch={BATCH_SIZE}")
    cpu_sequential = run_sequential(cpu_bound, cpu_args)
    print(f"  sequential: {cpu_sequential:.3f}s")
    cpu_threads = run_threads(cpu_bound, cpu_args, max_workers=BATCH_SIZE)
    print(f"  threads:    {cpu_threads:.3f}s")
    cpu_processes = run_processes(cpu_bound, cpu_args, max_workers=BATCH_SIZE)
    print(f"  processes:  {cpu_processes:.3f}s")

    print(f"io_bound: delay={IO_DELAY}, batch={BATCH_SIZE}")
    io_sequential = run_sequential(io_bound, io_args)
    print(f"  sequential: {io_sequential:.3f}s")
    io_threads = run_threads(io_bound, io_args, max_workers=BATCH_SIZE)
    print(f"  threads:    {io_threads:.3f}s")
    io_asyncio = asyncio.run(run_asyncio(io_bound, io_args))
    print(f"  asyncio:    {io_asyncio:.3f}s")

    result = {
        "cpu_bound": {
            "sequential": cpu_sequential,
            "threads": cpu_threads,
            "processes": cpu_processes,
        },
        "io_bound": {
            "sequential": io_sequential,
            "threads": io_threads,
            "asyncio": io_asyncio,
        },
    }
    # write_baseline resolves relative paths against MODULE_ROOT, not this
    # task's directory -- namespace the filename so it can't collide with
    # another task's *-local.json (e.g. task 08's profiling baseline).
    path = write_baseline("06-gil-decision-matrix/baseline-local.json", result)
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
