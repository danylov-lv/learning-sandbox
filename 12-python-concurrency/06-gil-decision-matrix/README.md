# 06 -- GIL Decision Matrix

## Backstory

Someone on your team took a CPU-bound data transform -- a pure-Python loop
doing math on every row -- and wrapped it in `asyncio.gather()` across a
batch of inputs, expecting the same kind of speedup they'd seen wrapping a
batch of HTTP calls the same way. It didn't get faster. It got slightly
*slower*, thanks to event-loop scheduling overhead on top of work that was
never going to overlap in the first place. They're now convinced "asyncio
doesn't really do concurrency" -- which is wrong in a specific, useful way:
asyncio (and threads) give you concurrency for work that spends its time
*waiting*, not work that spends its time *computing*. The Global Interpreter
Lock means only one thread executes Python bytecode at a time, no matter how
many threads or coroutines you throw at it -- unless the work in question
periodically lets go of the GIL, which I/O waits do and pure-Python compute
loops don't.

You know this conceptually already. This task makes you prove it with a
stopwatch, on your own hardware, instead of citing it as folklore. You'll
run the same two workloads -- one CPU-bound, one I/O-bound -- three ways
each (sequential, threads, processes; plus asyncio for the I/O case), read
off the actual numbers, and build the decision matrix that explains, with
evidence, when `asyncio.gather()` helps and when it's decoration.

## What's given

- `src/workloads.py` -- **fully implemented, not a stub.** Two
  module-top-level, picklable functions: `cpu_bound(n)` (a pure-Python
  trig/sqrt loop -- deliberately not vectorized with numpy, so it holds the
  GIL for its entire runtime) and `io_bound(delay)` (a `time.sleep(delay)`,
  standing in for a blocking network/disk call -- releases the GIL for its
  entire runtime). Constants `CPU_N`, `IO_DELAY`, `BATCH_SIZE` control how
  big each run is; don't need to touch this file.
- `src/runners.py` -- the scaffold you implement. Four functions, each
  running a batch of the same workload a different way and returning
  elapsed wall-clock seconds: `run_sequential`, `run_threads`
  (`ThreadPoolExecutor`), `run_processes` (`ProcessPoolExecutor`), and
  `run_asyncio` (async, I/O case only). Rich docstrings on every stub spell
  out the exact contract -- no solution code.
- `baseline.py` -- you run this (not the validator) once `runners.py` is
  implemented. It benchmarks both workloads across all the strategies on
  YOUR machine and writes the results to a gitignored `baseline-local.json`
  next to it.
- `ANSWER.md` -- an unfilled decision-matrix template: a table plus four
  sections asking you to explain the numbers, not just report them.

## What's required

1. Implement all four functions in `src/runners.py`. `run_sequential`,
   `run_threads`, and `run_processes` share the same signature
   (`workload, args_list, [max_workers]`) and are called with both
   workloads; `run_asyncio` is only ever called with `io_bound`.
2. Run `uv run python baseline.py` from this task's directory. It prints
   every elapsed number as it measures them and writes
   `baseline-local.json` (gitignored -- machine-specific, never committed).
3. Fill in every section of `ANSWER.md`, grounded in the numbers your own
   baseline run produced: the decision-matrix table, why threads don't help
   `cpu_bound`, why the GIL doesn't block `io_bound`'s speedup, when
   `ProcessPoolExecutor`'s overhead isn't worth paying, and your own rules
   of thumb.

### Windows gotcha: `ProcessPoolExecutor` and `spawn`

On Windows, `ProcessPoolExecutor` uses the `spawn` start method: each
worker process starts a fresh Python interpreter and re-imports whatever
module created the pool. If the code that constructs the pool isn't guarded
by `if __name__ == "__main__":`, importing that module in a child process
re-runs the whole script -- which spawns more children, which re-import the
module, recursively. `baseline.py` is already guarded correctly; if you
write your own scratch script to poke at `run_processes` by hand, guard it
the same way. `src/workloads.py`'s functions are module-top-level
specifically so they pickle cleanly across this boundary -- don't move them
inside another function or make them closures.

## Completion criteria

From this task's directory:

```bash
uv run python baseline.py
uv run python tests/validate.py
```

`tests/validate.py`:

- Reads `baseline-local.json`. If it's missing, `NOT PASSED` telling you to
  run `baseline.py` first.
- Checks the timing relationships the GIL predicts -- all relative to your
  own sequential run, never an absolute wall-clock number:
  - `cpu_bound`: `ProcessPoolExecutor` gives a real, meaningful speedup over
    sequential (separate GIL per process -> genuine parallelism).
    `ThreadPoolExecutor` stays close to sequential (one GIL, pure-Python
    bytecode never actually overlaps). The gap between the two speedups
    must be clearly present, not marginal.
  - `io_bound`: both `ThreadPoolExecutor` and `asyncio` give a large
    speedup over sequential (`time.sleep()` releases the GIL, so the wait
    genuinely overlaps).
  - Deliberately NOT checked: asyncio vs threads on `cpu_bound` -- both are
    GIL-bound there, roughly equal, and the difference between them is
    noise, not signal.
- Checks `ANSWER.md` has all five required sections, each filled with real
  content past the shipped `[fill in` placeholder, and references enough of
  the module's vocabulary (GIL, multiprocessing/process pool,
  threading/thread pool, cpu-bound, io-bound, pickle) to show the answers
  are grounded in what you actually measured.
- Prints `PASSED` with the four measured speedup ratios, or
  `NOT PASSED: <reason>` and exits 1 -- including when `runners.py` is
  still unimplemented (`NotImplementedError` surfaces as a clean message,
  no traceback).

## Estimated evenings

1-2

## Topics to read up on

- The GIL: what it actually serializes (bytecode execution), and which
  standard-library calls release it (I/O, `time.sleep`, many C-extension
  calls including most of numpy) versus which don't (a pure-Python loop)
- `concurrent.futures.ThreadPoolExecutor` vs `ProcessPoolExecutor` -- what
  each one actually parallelizes and at what cost
- Why `ProcessPoolExecutor` requires picklable callables and arguments, and
  what that costs per call
- `multiprocessing`'s `spawn` vs `fork` start methods, and why Windows only
  has `spawn`
- `asyncio.gather` combined with `asyncio.to_thread` as a bridge for
  blocking calls under an event loop (task 07 goes deeper on this)
- Why "more threads" or "asyncio.gather" is not a universal concurrency
  answer -- concurrency helps only when the work actually waits

## Off-limits

`.authoring/design.md` (at the module root) holds the harness API contract
and this task's exact verification margins -- spoilers. Don't read it
before finishing this task.
