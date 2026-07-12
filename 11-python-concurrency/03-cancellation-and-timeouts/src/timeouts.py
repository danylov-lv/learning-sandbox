"""s11.t03 -- cancellation and timeouts without leaks.

A timeout in asyncio is not a special mechanism -- it is cancellation with a
deadline attached. `asyncio.timeout()` / `asyncio.wait_for()` both work by
cancelling the awaited coroutine when the deadline passes, then raising
`TimeoutError` at the call site. Everything you know (or need to learn)
about cancellation applies directly to timeouts, and the two classic bugs
below both stem from treating cancellation as an inconvenience to swallow
rather than a signal to cooperate with.

Bug 1 -- the leaked resource. A timeout wrapper that looks reasonable at a
glance:

    async def guarded_operation(pool, work, timeout):
        resource = await pool.acquire()
        result = await asyncio.wait_for(work(), timeout)
        pool.release(resource)
        return result

When `work()` finishes in time, this releases the resource and all is well.
When `wait_for` times out, it raises `TimeoutError` -- and the `pool.
release(resource)` line, sitting AFTER the awaited call, never runs. The
resource is acquired forever. Multiply by every request that ever times
out and a long-running process quietly exhausts its connection pool, its
semaphore, whatever `pool` represents -- not from a crash, but from a code
path that only executes on the unhappy path. The fix is not "add a release
call in the except branch" (that only covers `TimeoutError`, not a plain
external cancellation) -- it's `finally`: release must run whichever way
the `try` block exits, because a `finally` block runs on a normal return,
on any raised exception, AND on `CancelledError` propagating through.

Bug 2 -- swallowed cancellation. A `try/except` guarding awaited work is
completely ordinary Python, and that's exactly what makes this bug easy to
write without noticing:

    async def guarded_operation(pool, work, timeout):
        resource = await pool.acquire()
        try:
            result = await asyncio.wait_for(work(), timeout)
        except Exception:
            result = None  # "handle" the failure and move on
        finally:
            pool.release(resource)
        return result

`asyncio.CancelledError` inherits from `BaseException`, not `Exception`, in
every Python version this task targets -- so a bare `except Exception:`
should not catch it. But `asyncio.wait_for` re-raises the wrapped
coroutine's `CancelledError` as `TimeoutError` on a timeout (in 3.11+), and
if the CALLER cancels `guarded_operation` itself (not a timeout -- an
external `task.cancel()`), that cancellation arrives INSIDE this function
as a real `CancelledError` at whatever await point is currently suspended.
An `except Exception:` around that await does nothing to it directly (it
propagates past `except Exception:`) -- the actual bug is broader: `except:`
(bare) or `except BaseException:` WOULD catch it, and so would code that
catches `CancelledError` explicitly and fails to re-raise it. Any of those
turns a cancellation request -- something that was supposed to stop this
coroutine -- into a swallowed no-op. The caller who cancelled you (because a
deadline passed upstream, because the user hit Ctrl-C, because a sibling
task in a `TaskGroup` failed) is now waiting on a task that refuses to stop.
Structured concurrency depends on cancellation being honored promptly;
eating it breaks that contract for everyone above you in the call stack.
The fix: never catch `CancelledError` without re-raising it (or catch only
the specific exception type you mean to handle, never something broad
enough to include it).

Bug 3's fix, not a bug -- the shielded finalizer. Sometimes a piece of
cleanup work genuinely must run to completion even when the operation
around it is being cancelled (e.g. flushing a write-ahead log entry, or
releasing a lock that would otherwise deadlock everyone else). Wrapping
that finalizer in a plain `await` does not protect it -- if the enclosing
coroutine is being cancelled, the cancellation propagates into whatever it
is currently awaiting, INCLUDING that finalizer, and the finalizer gets cut
off mid-way. `asyncio.shield()` wraps an awaitable so that cancelling the
outer await does not cancel the inner one -- the shielded coroutine keeps
running to completion (or to its own natural failure) even though the
`await asyncio.shield(...)` call site itself still raises `CancelledError`
back to the caller when the outer cancellation arrives. Note precisely what
shield does and does not do: it protects the shielded coroutine from being
cancelled; it does NOT protect the awaiting code from seeing
`CancelledError` at that await point (you still need to let that propagate,
per bug 2 above) -- it also does not stop cancellation of the shielded
coroutine from ITS OWN caller if that caller cancels it directly, only from
the cancellation of the *outer* await that's shielding it.

This module defines the scaffold. Implement `guarded_operation()` so that
none of the above three bugs are present: a timeout releases the resource,
an external cancellation propagates instead of being swallowed (after
releasing the resource), and an optional finalizer runs to completion via
`asyncio.shield` even when the operation is cancelled or times out.
"""

import asyncio


async def guarded_operation(resource_pool, work, timeout: float, finalizer=None) -> object:
    """Acquire a resource, run `work()` under a deadline, and guarantee the
    resource is released and cancellation is never swallowed -- regardless
    of how this call ends.

    Args:
        resource_pool: an object exposing `await resource_pool.acquire()`
            (returns a resource handle, and increments an internal
            `in_use` counter) and `resource_pool.release(handle)` (releases
            it, decrementing `in_use`). Acquire exactly one resource per
            call and release exactly the one you acquired, exactly once,
            no matter which of the three ways below this call ends.
        work: a zero-argument async callable, `await work()` runs the
            actual operation against the acquired resource. `work` does not
            take the resource as an argument -- it's expected to close over
            whatever it needs; this function's job is only to bound its
            runtime and guarantee cleanup around it.
        timeout: seconds to allow `work()` to run before it is cancelled
            and this call raises `TimeoutError`. Applies only to `work()`
            -- not to `resource_pool.acquire()` itself, and not to the
            optional `finalizer`.
        finalizer: an optional zero-argument async callable. If given, it
            must run to completion -- not be cut short -- even when this
            call is itself being cancelled or has timed out. Use
            `asyncio.shield` so cancellation of the surrounding operation
            does not also cancel the finalizer. If `finalizer` raises, that
            is a separate concern from the outcome of `work()` -- think
            about what an appropriate policy is (the docstring
            deliberately does not prescribe one; the validator only checks
            that the finalizer's own side effect completes).

    Returns:
        Whatever `work()` returned, on success (no timeout, no external
        cancellation).

    Raises:
        TimeoutError: `work()` did not complete within `timeout` seconds.
            The resource acquired at the start of this call has already
            been released by the time this is raised -- the caller must
            never need to release it themselves.
        asyncio.CancelledError: this call was itself cancelled from the
            outside (e.g. the caller cancelled the `Task` this coroutine is
            running in) before `work()` finished on its own and before the
            timeout fired. This must propagate to the caller -- it must
            NEVER be caught by a bare `except:`, an `except Exception:`, or
            an `except BaseException:` that fails to re-raise it. The
            resource acquired at the start of this call must still be
            released before the `CancelledError` propagates (put the
            release where it runs on every exit path, not only the timeout
            path -- see the module docstring's bug 1).

    Guarantees this implementation must uphold, all simultaneously:

    1. No resource leak, ever. Whether `work()` returns normally, raises,
       times out, or this coroutine is cancelled from outside, the resource
       acquired at the top of this call is released exactly once before
       control leaves this function. `resource_pool.in_use` must return to
       whatever it was before this call started, for every one of those
       exit paths.
    2. No swallowed cancellation, ever. `CancelledError` -- whether it
       arrives because of this function's own timeout firing, or because
       the caller cancelled the `Task` running this coroutine -- always
       ends up either propagating out of this function, or (in the timeout
       case specifically) being translated into the documented
       `TimeoutError`. It is never caught-and-discarded.
    3. The finalizer, if given, always runs to completion, even along the
       timeout and external-cancellation exit paths -- because it is
       awaited through `asyncio.shield`, not a bare `await`.
    """
    raise NotImplementedError
