# 02 -- TaskGroup Structured Concurrency

## Backstory

Somewhere in the pipeline you need to fan a batch of items out to a worker
coroutine and collect the results -- fetch a handful of upstream pages,
process a batch of records, whatever. You already know the pattern:

```python
async def fanout_broken(items, worker):
    tasks = [asyncio.create_task(worker(item)) for item in items]
    results = await asyncio.gather(*tasks)
    return results
```

This looks fine and works fine -- right up until one `worker(item)` call
raises. Two things go wrong at once, and neither is obvious from reading the
code:

1. **The siblings leak.** `asyncio.gather()` (without `return_exceptions=True`)
   re-raises the first exception it sees and returns control to the caller
   immediately. But the *other* tasks you created with `create_task()` were
   never cancelled -- they are still scheduled on the event loop, still
   running, completely detached from anything that will ever `await` them.
   `fanout_broken` has already returned control to its caller (probably via
   an exception), yet these orphaned tasks keep executing in the background,
   possibly for a long time, doing whatever they do -- writes, more requests,
   whatever their `await`s eventually resolve to -- with nobody watching.
2. **A second failure goes silent.** If more than one of those orphaned
   siblings eventually also raises, nothing is awaiting them anymore to
   observe it. Python logs a `Task exception was never retrieved` warning to
   stderr and moves on. The caller only ever learns about the *first*
   failure `gather()` happened to surface; every other failure among the
   fanned-out work is simply lost.

Neither of these is a `gather()` bug -- `gather()` is doing exactly what its
contract says. The bug is that `create_task()` + `gather()` gives you no
*scope* that owns the tasks it creates: nothing is responsible for making
sure every task this function started is either awaited, cancelled, or
accounted for by the time the function returns. That ownership is exactly
what "structured concurrency" means, and Python 3.11 gives you a primitive
built around it.

## What's given

- `src/fanout.py` -- a `run_fanout(items, worker)` stub. It currently
  `raise NotImplementedError`. The docstring spells out the exact guarantees
  the implementation must uphold and why the `create_task` + `gather` shape
  above violates them -- no solution code.
- `harness/common.py` (module root, shared, do not modify) -- in particular
  `run_async`, `snapshot_tasks`, and `leaked_tasks`, which the validator
  uses to prove nothing was left running. Fair game to use yourself while
  poking at your implementation by hand.

## What's required

Implement `async def run_fanout(items: list, worker) -> list` in
`src/fanout.py` using `asyncio.TaskGroup` so that:

1. **On full success**, every `worker(item)` runs concurrently, and the
   returned list holds each result in *input* order -- not completion
   order. (Two items with very different worker durations must not swap
   places in the output just because the faster one finished first.)
2. **On any single failure**, the moment one `worker(item)` raises, every
   other in-flight sibling is cancelled promptly -- not left to run to
   completion, not left orphaned in the background.
3. **The failure propagates** to the caller of `run_fanout`. Whether you let
   `TaskGroup`'s own `ExceptionGroup`/`BaseExceptionGroup` surface as-is, or
   catch it and re-raise the single underlying exception, is your call --
   just write down in `NOTES.md` which one your implementation does, since
   it changes what callers need to catch.
4. **No task is ever left alive.** Whether `run_fanout` returns normally or
   raises, every `asyncio.Task` it created must be finished (completed,
   cancelled, or failed and collected) by the time control returns to the
   caller -- nothing lingering for `leaked_tasks()` to find.

You have design freedom in exactly how you shape the body around
`asyncio.TaskGroup` -- how you track which result belongs to which input
item, how much (if anything) you catch and re-raise. The validator only
checks the four observable properties above.

## Completion criteria

Run, from this task's directory:

```bash
uv run python tests/validate.py
```

It:

- Fans a batch of items out to workers that each sleep briefly and return a
  value, and asserts the results come back correct **and in input order**,
  that the workers achieved real concurrency (a shared in-flight counter
  inside the worker must have peaked at a meaningful level, not run
  serially), and that no task was left alive afterward.
- Fans out a batch where one worker fails after a short delay and another
  ("long") worker would only flip a shared flag after a *much* longer
  sleep. Asserts `run_fanout` raises (either the `ExceptionGroup` or the
  underlying exception is accepted), that the long sibling's flag is
  **never** set (proof it was cancelled mid-sleep, not left running), and
  that no task remains alive afterward.
- Prints `PASSED` with the observed max concurrency, or
  `NOT PASSED: <reason>` and exits 1 on any failure -- including the stub
  still raising `NotImplementedError`.

## Estimated evenings

1

## Topics to read up on

- Structured concurrency, and what a "scope that owns its children" buys
  you over ad hoc `create_task`
- `asyncio.TaskGroup` (Python 3.11+)
- `ExceptionGroup` / `except*` (PEP 654)
- Task cancellation semantics -- how `CancelledError` propagates through an
  `await`
- `asyncio.gather`'s `return_exceptions` behavior, and why the default
  (`False`) still doesn't cancel siblings
- The `Task exception was never retrieved` warning and what it means

## Off-limits

`.authoring/` (at the module root) holds the harness API contract, mock-peer
semantics, and generation details for the whole module -- spoilers. Don't
read it before finishing this task.
