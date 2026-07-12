A structural walk-through, in order. No code -- just the shape.

1. Acquire the resource first, before anything that could time out or be
   cancelled. Hold onto the handle in a local variable; you'll need it
   again regardless of how the rest of this call goes.

2. Immediately wrap everything else in a `try` whose matching `finally`
   releases that resource. Not an `except` -- a `finally`. The release
   needs to happen whether `work()` finishes normally, raises some other
   exception, times out, or the whole call gets cancelled from outside.
   Putting the release after the risky call, instead of in a `finally`
   around it, is exactly the first bug this task is about.

3. Inside that `try`, run `work()` wrapped by your timeout mechanism of
   choice. Let whatever it raises propagate naturally -- a timeout should
   surface as `TimeoutError`, and an external cancellation should surface
   as `CancelledError`. Don't add an `except` here that catches either of
   those and does something other than let them through (after cleanup);
   that's the second bug.

4. If a `finalizer` was passed in, it needs to run — and run to completion
   — before this function's call truly ends, on every exit path (success,
   timeout, external cancellation alike). Put its call inside the same
   `finally` block as the resource release, wrapped in `asyncio.shield()`
   so that whatever cancellation triggered this `finally` block doesn't
   also cut the finalizer off partway through. Decide where relative to
   the resource release it belongs — think about whether the finalizer
   might reasonably need the resource still checked out, or whether release
   should always happen first.

5. After the `finally` block runs, whatever exception was in flight when
   you entered it (a `TimeoutError` you raised yourself, or a
   `CancelledError` that arrived from outside) needs to keep propagating.
   You don't need to manually re-raise anything you didn't explicitly
   catch with an `except` -- a bare `try/finally` (no `except`) already
   lets the original exception continue upward once the `finally` block
   finishes. Only add an `except` clause where you're deliberately
   translating one exception into another (the timeout-to-`TimeoutError`
   case), and even then, don't let it accidentally widen to catch
   `CancelledError` too.

Convince yourself of one more thing before you call it done: trace through
what happens if `work()` finishes successfully well within `timeout` --
does the resource still get released exactly once, does the finalizer (if
given) still run, and does the return value still make it back to the
caller? The happy path has to fall through the same `try/finally`
structure as the unhappy ones, not a separate code path bolted on beside
it.
