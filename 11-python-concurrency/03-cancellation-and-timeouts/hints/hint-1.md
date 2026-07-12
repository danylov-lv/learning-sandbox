Start from one fact and don't let go of it: cancellation in asyncio is
cooperative. Nothing forcibly yanks a coroutine's stack away mid-instruction
-- `task.cancel()` just arranges for `asyncio.CancelledError` to be raised
at the next point the coroutine is suspended on an `await`. What happens
after that is entirely up to the code that catches it (or doesn't).

A timeout is not a different mechanism from cancellation -- it's the same
mechanism with a clock attached. Something (`asyncio.timeout()`,
`asyncio.wait_for`) starts a timer, and when the timer fires, it cancels
the thing it's wrapping, exactly the way an external `task.cancel()` would.
Everything true about "what must happen when a coroutine gets cancelled" is
equally true about "what must happen when a coroutine times out" -- they're
the same event wearing a different name at the call site.

Given that, look at the stub's job again: acquire a resource, run work
under a deadline, hand back the result or the right error. Two different
things can go wrong here, and they are easy to conflate into a single "oops,
didn't clean up" bug report, but they are genuinely separate failures with
separate fixes:

- Something can be left **checked out** that should have been given back.
- Something can be **silenced** that should have been let through.

Find both before you write a line of the fix. Which line of a "reasonable
looking" implementation would fail to run if an exception -- of any kind --
came out of the awaited call? And separately: what exception type is
`CancelledError`, and what happens to code that assumes "catch Exception"
is broad enough to mean "catch anything that could go wrong here"?
