Once you know which function is the hot one, resist the urge to rewrite it
to be "faster" -- that's not the fix this task wants, and it's not what
`tests/validate.py` checks for. The check is about the event loop's
responsiveness, not the function's own runtime: it doesn't matter how many
milliseconds the function takes as long as those milliseconds don't happen
*on the event-loop thread* while other coroutines are waiting to run.

The fix is the same move task 01 makes you use on a differently-disguised
version of this exact problem: take the synchronous, CPU-bound call and
hand it to something that runs it off the event-loop thread, then `await`
the result back into the coroutine that needs it. `asyncio.to_thread(...)`
is the smallest change that does this -- it wraps a single call, returns an
awaitable, and needs nothing else in the surrounding pipeline to change.
`loop.run_in_executor(...)` does the same job with more control over which
executor runs it, if you want that.

Change exactly the one call site that calls the hot function inline; leave
the rest of the pipeline's shape alone. After the change, re-run `uv run
python tests/validate.py` -- the heartbeat tick count is what tells you
whether the loop actually stayed free, not a feeling that the code "looks"
fixed.
