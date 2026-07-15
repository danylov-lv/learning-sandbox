# Hint 3 -- concrete shape

Here's the fixed-window-counter shape in enough detail to implement it
without hunting for a snippet.

**One counter, atomically:**

A single Redis key represents "count of requests for this api_key in the
current window." The atomic step, for one counter, is:

1. `INCR` the key. Redis creates it at 0 and returns 1 if it didn't exist.
2. If the result of that `INCR` is exactly `1`, this call just created the
   key -- so, in the same atomic unit, attach a `PEXPIRE`/`EXPIRE` for the
   window length. Nothing else has touched this key yet, so there's no
   race about *whether* to set the TTL.
3. Compare the `INCR` result to the limit. If it's `<= limit`, the request
   is admitted. If it's `> limit`, reject -- and note that you've already
   incremented past the limit, which is fine; you just don't admit the
   request, you don't need to decrement anything back.

Steps 1-3 need to happen as one Lua `EVAL` (INCR, conditionally PEXPIRE,
return the new count) so that no other request's INCR can interleave
between "I just created this key" and "I set its TTL," and so the
increment-and-compare is indivisible. This is exactly the pattern that
makes "exactly RATE_LIMIT admitted under a concurrent burst" true: every
concurrent request gets a distinct, serialized integer back from INCR (1,
2, 3, ... N) because Redis itself serializes command execution -- your job
is just to not split that serialization across multiple round trips.

**Retry-After:** when you reject, read the key's remaining TTL (Redis
`PTTL`/`TTL` on the same key, or return it from the same Lua script to
save a round trip) and round up to whole seconds for the header.

**Two counters, ordered:**

Apply that exact pattern twice, with two different keys (different name,
different window length) for the same `api_key` -- one under something
like `.../rate/<key>` with `RATE_WINDOW_SEC`, one under `.../quota/<key>`
with `QUOTA_WINDOW_SEC`. Since they're separate keys, each's atomic
INCR+PEXPIRE is independent of the other.

The ordering that satisfies "a rate rejection must not consume quota
budget" without any extra undo logic: **check-and-increment the rate
counter first.** If that alone already puts you over `RATE_LIMIT`, return
the rate-limited 429 immediately and never touch the quota counter at all
this request. Only if the rate check passes do you go on to
check-and-increment the quota counter -- if *that* one is now over
`QUOTA_LIMIT`, return the quota-exceeded 429 instead. Because you never
increment quota when rate rejects, a rate-limited request costs nothing
against the longer-window budget, with no compensating decrement required
anywhere.

Everything above needs zero shared code beyond what's given: the two
counters are just two Redis keys under `REDIS_PREFIX`, keyed by `api_key`,
each running the same one-round-trip INCR+conditional-PEXPIRE+compare
logic against its own limit and window.
