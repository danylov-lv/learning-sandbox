Treat this as two separate bugs, not one. Fixing only one of them will still
fail the validator, just for a different reason than before -- so before
reaching for any API, make sure you can say out loud which requirement each
half of your implementation is satisfying.

**Bug 1: nothing is concurrent yet.** A coroutine that does
`await session.get(...)` inside a `for` loop, once per path, never has more
than one request in flight. The loop body doesn't resume to its next
iteration until the `await` it's currently sitting on resolves -- so the
second request is never even *sent* until the first response has fully
arrived. "Concurrent" here doesn't mean "written with `await`" -- it means
"multiple `await`-able things are outstanding against the peer at the same
moment, and something is waiting on all of them together." What would it
take to have all N GET requests actually in flight before any of them has to
finish?

**Bug 2: the loop's only thread cannot also run your blocking function.**
Once requests are concurrent, each response still needs
`blocking_parse(body)` run on it. That call is synchronous and has no
`await` inside it by design -- calling it directly from a coroutine body
means the event loop's one thread is now inside that function, unable to do
anything else (poll sockets, resume other coroutines, fire timers) until it
returns. The fix isn't a different way of calling `blocking_parse` from the
same thread -- it's getting it to run on a *different* thread while your
coroutine `await`s the outcome. What in the standard library lets a
coroutine hand a synchronous callable to another thread and get an
awaitable back for the result?

Both fixes compose: you'll end up with something concurrent over paths,
where each path's own unit of work does a network `await` followed by an
offloaded-parse `await`.
