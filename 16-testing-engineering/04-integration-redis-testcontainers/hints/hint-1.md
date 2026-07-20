# Hint 1 -- direction

You are not implementing anything here -- `RateLimiter` and `DedupFilter`
in `src/impl.py` are correct and already atomic. Your job is to write a
test suite that would *notice* if someone broke them later. Read the two
docstrings again, slowly, and for each sentence in them ask: "what is the
simplest wrong implementation that would still make this sentence true in
the one obvious test I'd write first?"

For example, "the first `limit` calls return True" is easy to test with a
loop and an assert. But a test that stops there also passes against an
implementation that never sets a TTL at all -- the counter just grows
forever and the window never resets, which is a real production bug (a
client that gets rate-limited once stays limited forever). The happy path
alone can't see that; you need a second test that looks at the *key
itself*, not just the return value of `allow()`.

Same instinct applies everywhere in this task: atomicity, key
namespacing, and TTL expiry are all things that "call it once, check the
obvious thing" will not exercise. Before writing any test code, list the
behaviors in the docstrings that are NOT covered by a single, first-call
check, and write those down as separate test names first.

Also: this integration suite talks to a real, ephemeral Redis container
(see `tests/conftest.py`). Every test should assume a clean database (it
is -- flushed automatically) and use its own key names so tests can't
interfere with each other.
