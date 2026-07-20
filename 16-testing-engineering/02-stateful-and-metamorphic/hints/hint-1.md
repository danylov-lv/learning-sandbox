A single `@given(...)` test that calls `put` once and `get` once cannot
catch most of the bugs a cache like this can have. Eviction order and
recency are properties of a SEQUENCE of operations -- "does this cache
still remember the right things after fifty puts and gets in some order"
-- not of any one call. That is exactly the gap stateful testing fills:
instead of generating one input, Hypothesis generates a whole SEQUENCE of
operations (a "rule" per operation type) and checks an invariant holds
after every step, shrinking a failing sequence down to the shortest one
that still reproduces the bug.

Before writing any Hypothesis code, write out on paper (or in a comment)
what a MODEL of this cache would look like -- the simplest possible data
structure that captures "what should `get` return right now" and "what
should get evicted next," without reimplementing the real cache's
internals. An ordered structure that tracks recency, plus a per-key
expiry deadline, is enough. You are not trying to write a second TTLCache;
you are trying to write the dumbest possible thing you can compare the
real one against.

Also decide up front how you will control time. `TTLCache`'s `clock`
parameter takes any zero-argument callable returning a float. The
simplest deterministic clock for a test is a one-element mutable
container you close over, e.g. `box = [0.0]; clock = lambda: box[0]`, and
"advancing the clock" is just `box[0] += delta`.
