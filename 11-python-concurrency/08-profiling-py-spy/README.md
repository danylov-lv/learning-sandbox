# 08 -- Profiling with py-spy

## Backstory

An async worker in your fleet pins one CPU core and everything else about it
stalls -- other coroutines in the same process fall behind, a metrics
ticker that's supposed to print once a second prints in bursts, throughput
is a fraction of what the concurrency setting and the (simulated) I/O
latency alone would predict. Nobody can point at the line. The code reviews
clean: `asyncio.TaskGroup`, a bounded producer/consumer queue, a handful of
small pipeline steps that each look about as busy as the others. `async
def` is everywhere it should be.

That's exactly the shape of bug reading the source won't find quickly --
somewhere in the pipeline, one ordinary-looking synchronous helper is doing
real CPU work directly on the event-loop thread, and nothing in the code
announces which one. In production you wouldn't `git blame` your way to it
either; you'd attach a sampling profiler to the live process and look at
where the samples actually pile up. That's the job here: **profile a
running process with `py-spy`, not by guessing.**

## What's given

- `src/app.py` -- a runnable async ingestion worker. `uv run python
  src/app.py` starts it as a long-lived process (prints its PID
  immediately, then runs for several seconds to tens of seconds depending
  on `--records`/`--duration`) -- long enough to attach a profiler to while
  it's alive. It also exposes `async def run_workload(...) -> stats` as a
  plain importable entrypoint, which is what `tests/validate.py` drives
  in-process. The module docstring describes what the pipeline does; it
  deliberately does *not* say which function is the bottleneck -- that's
  what you're profiling to find.
- `ANSWER.md` -- unfilled. You'll record what you found and how you fixed
  it here; `tests/validate.py` checks it's actually filled in.
- `tests/validate.py` -- the validator. It does **not** run py-spy itself
  (see the caveat below for why). It checks two things independently: that
  the event loop stays responsive while `run_workload()` runs (a concurrent
  heartbeat coroutine's tick count, same technique as task 01), and that
  `ANSWER.md` names the function you found and shows you actually used
  py-spy to find it.
- `harness/common.py` (module root, shared, do not modify) -- `run_async`,
  `snapshot_tasks`/`leaked_tasks`, pass/fail printing. Fair game to poke at
  by hand; not something `src/app.py` itself needs to import.

## What's required

1. **Start the app**: `uv run python src/app.py` (from this task's
   directory). It prints `PID=<pid>` on its first line -- note it.
2. **Profile the live process**, from a second terminal, while it's still
   running. Two py-spy tools do this without any code changes to the
   target:
   - `py-spy record -o scratch/profile.svg --pid <pid>` -- samples the
     process for a while and writes a flamegraph SVG you can open in a
     browser. Let it sample for several seconds, then let it finish (or
     stop it), and open `scratch/profile.svg`.
   - `py-spy dump --pid <pid>` -- a one-shot snapshot of every thread's
     current stack. Run it a few times in a row; whatever function keeps
     showing up at the top of the stack across repeated dumps is a strong
     signal on its own, no SVG required.
   `scratch/` is gitignored -- put profiler output there, not under `src/`.
3. **Identify the hot function** from what py-spy shows you (a wide,
   repeated self-time frame in the flamegraph, or a function that keeps
   appearing at the top of `py-spy dump` snapshots) and record it in
   `ANSWER.md`, along with how you found it and what you changed.
4. **Fix `src/app.py`** so the function you found stops running inline on
   the event-loop thread -- move it off that thread (or make it cheap
   enough that the loop never notices), without changing what the pipeline
   computes. `tests/validate.py`'s heartbeat check is what tells you
   whether the fix actually worked.

### Windows privilege caveat

py-spy attaches to another process's memory to sample it, which on Windows
usually requires the profiler and the target to run with matching
privilege. If `py-spy dump --pid <pid>` (or `py-spy record`) reports a
permission/access-denied error, re-run your terminal **as Administrator**
and try again from there -- both the `uv run python src/app.py` process and
the `py-spy` command need to be launched from an elevated shell (or neither
does, on some setups) for the attach to succeed. This is an OS/profiler
limitation, not something `src/app.py` or `tests/validate.py` can work
around; the validator never shells out to py-spy for exactly this reason.

## Completion criteria

Run, from this task's directory:

```bash
cd 08-profiling-py-spy
uv run python tests/validate.py
```

It:

- Drives `run_workload()` directly (no subprocess, no py-spy involved) and
  confirms the records it reports processing match what was asked for --
  guards against a "fix" that skips work instead of actually offloading it.
- Runs a heartbeat coroutine concurrently with `run_workload()` and checks
  its tick count didn't collapse -- the same technique task 01 uses to
  catch a blocking call running inline on the event-loop thread, without
  ever asserting an absolute wall-clock number.
- Confirms nothing `run_workload()` spawned was left running afterward.
- Checks `ANSWER.md` names the function you found, isn't a stub, and shows
  you actually used py-spy (not the source diff) to find it.
- Prints `PASSED` with the tick count and elapsed time, or
  `NOT PASSED: <reason>` and exits 1 on any failure.

## Estimated evenings

1

## Topics to read up on

- `py-spy record` (sampling profiler -> flamegraph SVG) and `py-spy dump`
  (one-shot stack snapshot) against a live PID
- How to read a flamegraph: width means samples/time, not chronological
  order; a wide *self-time* frame near the top of a stack is where the
  process is actually spending its cycles, not just passing through
- Sampling profilers vs. deterministic profilers (`cProfile`) -- why
  attaching externally to a running process is a different tool for a
  different situation than instrumenting code you're about to run
- Why a function with no `await` inside it, called from a coroutine, blocks
  every other coroutine in the process for its entire duration -- same
  mechanism as task 01, different disguise
- `asyncio.to_thread` / `loop.run_in_executor` as the fix once you've found
  the culprit

## Off-limits

`.authoring/design.md` (module root) holds the harness API contract and
generation details for the whole module -- spoilers. Don't read it before
finishing this task.
