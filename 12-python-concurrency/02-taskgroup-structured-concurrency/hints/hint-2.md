The primitive you want is `asyncio.TaskGroup` (Python 3.11+), used as an
async context manager:

```
async with asyncio.TaskGroup() as tg:
    ...
```

Two things make it the scope described in hint-1, not just a nicer
`gather()`:

**It cancels its own children on first failure.** The moment any task
spawned inside the `async with` block raises an exception (other than
`asyncio.CancelledError`), the TaskGroup cancels every other task it is
still tracking -- automatically, without you writing any cancellation logic
yourself. This is the mechanism, not a side effect: it's *why* TaskGroup can
promise "nothing outlives this block."

**The `async with` block itself does not exit until every child is
resolved.** Exiting the block -- by falling off the end, or by an exception
propagating out of it -- blocks (in the async sense: `await`s) until every
task the group knows about has either completed or been cancelled and
observed. That's the ownership guarantee made concrete: you cannot get past
`async with asyncio.TaskGroup() as tg: ...` with a child still unresolved.

Failures are reported back to you as an `ExceptionGroup` (or
`BaseExceptionGroup`, if a `BaseException` like `KeyboardInterrupt` was
involved) raised from the `async with` block once every child has settled --
never as a single ad hoc exception the way `gather()` does it, and never
silently. Python's `except*` syntax (PEP 654) exists specifically to filter
by exception type inside a group, but you don't need `except*` inside
`run_fanout` itself unless you choose to catch and re-inspect what happened
-- letting the group propagate unchanged is also a valid choice (see
guarantee 3 in the docstring).

Look up: how you get a `Task` handle for spawning inside a TaskGroup (it has
its own method for this, distinct from the bare `asyncio.create_task`), and
how you'd read a result back off that handle once the `async with` block has
exited.
