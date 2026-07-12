Start by naming precisely what `create_task()` + `gather()` is missing,
because "TaskGroup is just gather but nicer" is not the right mental model.

`create_task()` schedules a coroutine to run on the event loop and hands you
back a `Task` handle -- but from that moment on, the task's lifetime is
*not* tied to anything. It runs, it finishes (or fails, or keeps running
forever), independent of whatever function called `create_task()`. If that
function returns -- normally or via an exception -- without every task it
created being awaited or cancelled, those tasks don't know or care. They
just keep going, scheduled on the same loop, doing whatever they do, with
no code left anywhere that is "responsible" for them.

`gather()` doesn't fix this. It's a convenience for *awaiting several
awaitables and collecting results* -- but awaiting is not owning. When one
of the gathered tasks raises (and you didn't pass `return_exceptions=True`),
`gather()` re-raises that exception to whoever awaited it and returns. The
other tasks you handed to `gather()` are not touched by this at all -- they
were independent tasks before you called `gather()`, and they remain
independent tasks after `gather()` raises and you stop looking at them.

"Structured concurrency" is the idea that a block of code should be a
*scope*: a lexical region that owns everything it starts, such that by the
time you exit that region (however you exit it -- return, exception, doesn't
matter), nothing it started is still running unaccounted for. Think about
what a scope with that property would need to do the instant one of its
children fails -- not eventually, not "next time someone checks," but
immediately, to the rest of its own children.
