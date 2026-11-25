Start by separating the two bugs -- they don't share a fix, and reaching for
the wrong tool for either one leaves you stuck.

**Bug 1** is about a coroutine that needs to call something synchronous and
genuinely blocking. "Genuinely blocking" is the key phrase: `blocking_lib`
holds whatever OS thread calls it hostage for real wall-clock time, with no
`await` point inside it for the event loop to reclaim that thread. You
cannot fix this by rearranging `await`s around the call -- there's nothing
to `await`, because `blocking_lib` isn't a coroutine and never yields
control back on its own. The only fix is moving the call itself off the
event loop's thread entirely, onto a different thread, and having the
coroutine `await` a handle to that other thread's result. Python's stdlib
gives you more than one way to run something on another thread from async
code -- look at what `asyncio` itself offers for "run this sync callable on
a worker thread and give me an awaitable back."

Once you can offload one call, think about what happens with `N` items and
a `max_workers` cap. Offloading badly (spawn a thread per item, no limit)
still isn't safe just because it's off the loop's thread -- threads,
sockets, file handles, whatever `blocking_lib` touches underneath, are all
finite. You need a mechanism that limits how many offloaded calls are
*actually running* at once, independent of how many items you have queued
up.

**Bug 2** is a much smaller problem once you see it clearly: a coroutine
function, called like a normal function, does not run its body. It builds a
coroutine *object* and hands it back inert. Something has to actively drive
that object to completion on an event loop before any of its code executes.
`sync_entrypoint` is a plain function with no event loop of its own --
what's the standard stdlib entry point for "run this coroutine to
completion, from a synchronous context with no loop yet"?
