"""Shared helpers for module 11 (Python concurrency: asyncio event-loop
internals) validators, generators, and task scaffolds.

Every validator prints PASSED or `NOT PASSED: <reason>` and exits 0/1; no
tracebacks reach the learner. Run these host-side via `uv run`. This module
is pure Python — there is no docker stack for module 11 — but every
third-party import (aiohttp, psutil, numpy) is still lazy inside the function
that needs it, so importing `harness.common` never has side effects.

Two concurrency-specific helper families live here, both built for
validators that must prove structured-concurrency discipline rather than
just a correct return value:

- **Leaked-task detection** (`snapshot_tasks` / `leaked_tasks`): a validator
  takes a snapshot of live `asyncio.Task`s before running the code under
  test and diffs against a snapshot taken after. Any task that is neither in
  the "before" set nor finished is a leak — e.g. a `create_task()` whose
  handle was dropped without being awaited or cancelled. This is how tasks
  01 (blocking-the-loop rescue), 03 (cancellation/timeouts), and the
  capstone assert "no leaks" instead of eyeballing it.
- **Peak-memory measurement** (`measure_peak_memory`): runs a coroutine
  under `tracemalloc` and reports the peak *traced* allocation in bytes.
  This is deliberately used instead of RSS (`rss_bytes`, kept as a secondary
  signal) because RSS is OS-dependent and noisy (allocator arenas, page
  reuse), while traced peak allocation is portable across Windows/Linux/Mac
  and reproducible run-to-run for tasks like 04 (backpressure) where the
  whole point is bounding in-flight memory.
"""

import json
import sys
import time
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = MODULE_ROOT / "data"
GROUND_TRUTH_PATH = DATA_DIR / "ground-truth.json"


# --------------------------------------------------------------------------
# Pass / fail plumbing (identical semantics to module 10)
# --------------------------------------------------------------------------

def not_passed(reason):
    print(f"NOT PASSED: {reason}")
    sys.exit(1)


def passed(msg=""):
    print(f"PASSED{': ' + msg if msg else ''}")
    sys.exit(0)


def guarded(fn):
    """Decorator: wrap a validator body so unexpected exceptions become
    NOT PASSED instead of a raw traceback."""
    import functools

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except SystemExit:
            raise
        except NotImplementedError:
            not_passed("scaffold not implemented yet (NotImplementedError)")
        except Exception as e:
            not_passed(f"unexpected error: {type(e).__name__}: {e}")

    return wrapper


def _last_line(text):
    """Last non-empty line of a subprocess stream or error text -- enough to
    say WHY a run failed without leaking a full traceback/stack dump."""
    lines = [ln for ln in (text or "").splitlines() if ln.strip()]
    return lines[-1] if lines else "(no output)"


# --------------------------------------------------------------------------
# Benchmark helpers (relative timing against a machine-local baseline)
# --------------------------------------------------------------------------

def time_it(fn, *args, **kwargs):
    """Call fn(*args, **kwargs), return (result, elapsed_seconds). Wall clock
    via time.perf_counter. Timing checks are always relative to a machine-
    local baseline (see read_baseline / write_baseline), never absolute."""
    start = time.perf_counter()
    result = fn(*args, **kwargs)
    return result, time.perf_counter() - start


def write_baseline(path, obj):
    """Write a machine-local baseline (e.g. reference timings) to a gitignored
    `*-local.json` file. Path may be relative to the module root."""
    p = Path(path)
    if not p.is_absolute():
        p = MODULE_ROOT / p
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=2), encoding="utf-8")
    return p


def read_baseline(path):
    """Read a machine-local baseline written by write_baseline, or None if it
    doesn't exist yet (the baseline step hasn't been run)."""
    p = Path(path)
    if not p.is_absolute():
        p = MODULE_ROOT / p
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# Ground truth
# --------------------------------------------------------------------------

def load_ground_truth():
    if not GROUND_TRUTH_PATH.exists():
        not_passed(f"ground truth not found at {GROUND_TRUTH_PATH} — run `uv run python generate.py` first")
    return json.loads(GROUND_TRUTH_PATH.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# Async execution
# --------------------------------------------------------------------------

def run_async(coro):
    """Run `coro` to completion via `asyncio.run` and return its result. If a
    loop is already running in this thread (e.g. called from inside async
    code by mistake), NOT PASSED with a clear message instead of raising
    asyncio's own `RuntimeError: asyncio.run() cannot be called from a
    running event loop`."""
    import asyncio

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    else:
        not_passed(
            "run_async() called from inside a running event loop — "
            "await the coroutine directly instead of calling run_async()"
        )


# --------------------------------------------------------------------------
# Leaked-task detection
# --------------------------------------------------------------------------

def snapshot_tasks():
    """Return the set of currently-alive asyncio.Task objects, EXCLUDING the
    task calling this function. Only meaningful when called from inside a
    running event loop (e.g. from within a coroutine under `run_async`)."""
    import asyncio

    current = asyncio.current_task()
    return {t for t in asyncio.all_tasks() if t is not current}


def leaked_tasks(before):
    """Given a `before` set from `snapshot_tasks()`, return the list of tasks
    alive right now that were NOT in `before` and are not yet done — i.e.
    tasks created and abandoned (never awaited, cancelled, or otherwise
    reaped) during the code under test. Validators assert this is `[]`."""
    import asyncio

    current = asyncio.current_task()
    after = {t for t in asyncio.all_tasks() if t is not current}
    return [t for t in after - before if not t.done()]


# --------------------------------------------------------------------------
# Memory measurement
# --------------------------------------------------------------------------

def measure_peak_memory(async_fn, *args, **kwargs):
    """Run `async_fn(*args, **kwargs)` to completion (via `asyncio.run`,
    under `tracemalloc`) and return `(result, peak_bytes)`, where `peak_bytes`
    is the peak traced allocation observed during the run. Portable across
    OSes, unlike RSS — used to bound in-flight memory for tasks like
    backpressure/bounded-queue where an unbounded producer would blow past a
    small multiple of the bounded version's peak.

    Must be called from a thread with no event loop already running (it
    drives its own `asyncio.run`), same constraint as `run_async`.
    """
    import asyncio
    import tracemalloc

    tracemalloc.start()
    try:
        result = asyncio.run(async_fn(*args, **kwargs))
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    return result, peak


def rss_bytes():
    """Current process RSS in bytes via psutil — an optional/secondary signal
    alongside `measure_peak_memory`'s tracemalloc peak (RSS is OS-dependent
    and noisier: allocator arenas, page reuse, etc.)."""
    import os

    import psutil

    return psutil.Process(os.getpid()).memory_info().rss
