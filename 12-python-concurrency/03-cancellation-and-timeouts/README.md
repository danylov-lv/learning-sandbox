# 03 -- Cancellation and Timeouts

## Backstory

Your async scraper calls out to a peer that is sometimes slow, sometimes
never responds at all. You wrap the call in a timeout so one hung request
can't stall the whole pipeline. Reasonable so far -- and this is exactly
where two of the most common asyncio bugs live, because both look correct
at a glance and both only show up under conditions your happy-path testing
never exercises.

**Bug 1 -- the leaked resource.** A timeout wrapper that acquires a
connection, runs the call, and releases the connection afterward:

```python
async def guarded_operation(pool, work, timeout):
    resource = await pool.acquire()
    result = await asyncio.wait_for(work(), timeout)
    pool.release(resource)
    return result
```

When `work()` finishes in time, this releases the resource and everything's
fine. When `wait_for` times out, it raises `TimeoutError` -- and the
`pool.release(resource)` line, sitting *after* the call that just raised,
never executes. The resource stays checked out forever. Nothing crashes.
Nothing logs an error. The pool just quietly runs out of connections after
enough timeouts have happened, and by the time anyone notices, the
"leak" is scattered across thousands of past requests with no single stack
trace to blame.

**Bug 2 -- swallowed cancellation.** A `try/except` around the same call,
written by someone who wanted to "handle" the timeout gracefully instead
of letting it propagate:

```python
async def guarded_operation(pool, work, timeout):
    resource = await pool.acquire()
    try:
        result = await asyncio.wait_for(work(), timeout)
    except Exception:
        result = None
    finally:
        pool.release(resource)
    return result
```

This one fixes bug 1 (the `finally` releases the resource on every path) --
but introduces a subtler problem the moment `guarded_operation` itself gets
cancelled from outside (a sibling task in a `TaskGroup` failed, the caller's
own deadline passed, the process is shutting down). `asyncio.CancelledError`
is not an `Exception` subclass, so a literal `except Exception:` doesn't
catch it directly here -- but the same instinct, written slightly wider
(`except:`, `except BaseException:`, or an explicit `except
CancelledError:` that forgets to re-raise), does. Any of those turns a
cancellation request into a swallowed no-op: the caller who cancelled you,
for a reason, is left waiting on a task that silently refuses to stop.
Structured concurrency (as in task 02's `TaskGroup`) depends on
cancellation propagating promptly through every layer -- eating it anywhere
in the chain breaks that guarantee for everyone above you.

There's a third piece to this task that is not a bug to fix but a tool to
use correctly: sometimes a bit of cleanup genuinely must finish even while
everything around it is being torn down -- flushing a log entry, releasing
a lock cleanly instead of leaving it to a deadlock-detector. A plain
`await` on that cleanup gets cancelled right along with everything else.
`asyncio.shield()` decouples a shielded awaitable's fate from the
cancellation of whatever's currently awaiting it, so the cleanup finishes
even when the surrounding operation doesn't.

## What's given

- `src/timeouts.py` -- a single function, `guarded_operation()`, currently
  `raise NotImplementedError`. Its docstring spells out, guarantee by
  guarantee, what "no leak" and "no swallowed cancellation" mean here, and
  walks through why each of the two bugs above is a bug.
- `harness/common.py` (module root) -- `run_async`, `snapshot_tasks`,
  `leaked_tasks`, `guarded`, `not_passed`, `passed`. No mock peer needed for
  this task; the resource pool being guarded is a small in-memory stand-in
  supplied by the validator, not a network call.

## What's required

Implement `async def guarded_operation(resource_pool, work, timeout,
finalizer=None) -> object` in `src/timeouts.py` so that:

1. It acquires exactly one resource from `resource_pool` (via `await
   resource_pool.acquire()`) before running anything else, and releases it
   (via `resource_pool.release(handle)`) exactly once, no matter how the
   call ends -- `work()` finishes normally, `work()` times out, or the call
   itself is cancelled from outside.
2. On timeout (`work()` still running when `timeout` seconds have elapsed):
   the in-flight work is cancelled, the resource is released, and
   `guarded_operation` raises `TimeoutError` -- never leaves the resource
   checked out, never raises something else instead.
3. On external cancellation (something outside calls `.cancel()` on the
   task running `guarded_operation`, independent of the timeout):
   `CancelledError` propagates to the caller -- after the resource has been
   released, never before, and never swallowed by a catch-all `except`.
4. If a `finalizer` (an async, zero-argument callable) is given, it runs to
   completion -- not partially, not skipped -- even along the timeout and
   external-cancellation exit paths, via `asyncio.shield`.

No reference implementation exists anywhere in this repository. The
docstring in `src/timeouts.py` is deliberately thorough about the
guarantees required and thin on how to satisfy them -- that part is yours.

## Completion criteria

Run, from this task's directory:

```bash
uv run python tests/validate.py
```

It exercises three scenarios against a small in-memory `ResourcePool` the
validator defines itself (tracks an `in_use` counter, starts at 0):

- Fires `guarded_operation` with `work()` sleeping far longer than
  `timeout` -- asserts `TimeoutError` is raised, `pool.in_use` is back to
  0, and no `asyncio.Task` was left running behind it.
- Starts `guarded_operation` as a `Task` and cancels it mid-`work()` --
  asserts awaiting that task raises `CancelledError` (propagated, not
  eaten) and `pool.in_use` is back to 0.
- Passes a `finalizer` that sets a flag after a short sleep, then triggers
  a timeout -- asserts the flag ended up set (the finalizer ran to
  completion despite the surrounding cancellation) and the resource was
  still released.

Prints `PASSED: <summary>` and exits 0 on success, or a single
`NOT PASSED: <reason>` line and exits 1 -- including while the stub still
raises `NotImplementedError`.

## Estimated evenings

1

## Topics to read up on

- Cooperative cancellation in asyncio -- what `Task.cancel()` actually does
  and when `CancelledError` gets raised
- `asyncio.timeout()` vs `asyncio.wait_for` -- what each guarantees about
  the wrapped coroutine once the deadline passes
- `try` / `except` / `finally` semantics on exception propagation, and why
  `finally` is the only block guaranteed to run on every exit path
- The exception hierarchy: why `asyncio.CancelledError` inherits from
  `BaseException`, not `Exception`, and what that means for `except
  Exception:`
- `asyncio.shield()` -- what it decouples and what it deliberately does not
  protect against
- Structured concurrency and why swallowed cancellation breaks it (ties
  back to task 02's `TaskGroup`)

## Off-limits

`.authoring/` (at the module root) holds the harness API contract, the
mock-peer semantics, and other tasks' design spoilers. Don't read it before
finishing this task.
