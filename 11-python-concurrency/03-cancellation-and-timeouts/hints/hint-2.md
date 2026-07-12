Four names to go read the docs for, in the order you'll reach for them:

**`asyncio.timeout()` (or `asyncio.wait_for`).** Either bounds an awaited
call to a deadline and raises `TimeoutError` if it's exceeded, cancelling
whatever was still running underneath. `wait_for` is the older, function-
style API (`await asyncio.wait_for(coro, timeout)`); `asyncio.timeout()` is
the newer context-manager style. Either is a legitimate choice here --
read what each one guarantees about the state of the wrapped coroutine
once the deadline passes and control returns to you (has it been awaited
to completion, cancelled and awaited, or something else?).

**`try` / `finally`.** The only construct that reliably runs cleanup code
on every exit path from a `try` block -- normal return, any raised
exception, and `CancelledError` propagating through. An `except` clause,
by contrast, only runs for the exception types it names (or their
subclasses) -- and only if control actually reaches that `except`, which
matters once you get to the next item.

**Re-raising `CancelledError`.** Check what `asyncio.CancelledError`
inherits from in the Python versions this task targets (3.11+), and
compare that to what a bare `except Exception:` actually catches. Then
think about the more common way this bug sneaks in anyway: catching
`CancelledError` explicitly (or catching something broader like `except
BaseException:`) to run some "on failure" logic, and simply not ending
that branch with `raise`.

**`asyncio.shield()`.** Wraps an awaitable so that cancelling the *outer*
await doesn't cancel the *inner* one -- the shielded coroutine keeps
running toward its own completion independent of what happens to whoever
is awaiting it. Read carefully what shield does NOT do: it doesn't stop
`CancelledError` from being raised at the `await asyncio.shield(...)` call
site itself when the outer cancellation happens -- it only decouples the
shielded coroutine's fate from that particular await getting cancelled.
That distinction is exactly what makes it useful for a finalizer: you want
the finalizer to finish, but you don't want it to silently swallow the
fact that the surrounding operation was cancelled.
