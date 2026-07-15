# Hint 2 -- naming the pieces

There are three standard shapes for this kind of limiter. Know the
trade-offs even though you only need to pick and defend one:

- **Fixed window counter** -- one counter per key per window-slot (e.g.
  "this key, this 2-second bucket"), with the key itself expiring at the
  end of the window. Simple, cheap (one counter, one TTL), but has a
  well-known edge case: a burst straddling the boundary between two windows
  can admit up to ~2x the limit in a short span. Acceptable for a lot of
  real systems, and it's the shape this task's completion criteria are
  written around (a single window's worth of requests, then a reset).
- **Sliding-window log** -- store a timestamp per request (e.g. in a
  sorted set), trim anything older than the window on each check, and
  count what's left. Exact, no boundary problem, but O(window size) memory
  and work per key.
- **Token bucket** -- a bucket refills at a steady rate up to some
  capacity; each request consumes a token if available. Smooths bursts
  differently (allows saved-up capacity to be spent quickly, then
  throttles to the refill rate) and is common for the "burst + sustained"
  shape specifically -- which is suggestive, given this task has exactly
  that shape (rate = burst cap, quota = sustained cap).

Whichever you pick, the atomicity requirement is the same: the read
(current count / current token count) and the write (increment / consume)
must happen as a single operation from Redis's point of view, not as two
commands issued by your application code with an await in between.

Two ways to get that:

1. **A Lua script run via `EVAL`/`EVALSHA`.** Redis executes the whole
   script as one atomic unit -- no other command interleaves partway
   through. This is the general-purpose answer and works for any of the
   three algorithms above, including "set an expiry only if this is the
   very first increment," which a single `INCR` alone can't express.
2. **A pipeline built around the fact that `INCR` itself is atomic and
   returns the *new* value.** If you `INCR` first and look at what it
   returns, you never have to separately GET a stale value -- the
   increment IS the read. You still need a second command to attach a TTL
   the first time the key is created, and that second command doesn't
   need to be atomic *with* the INCR as long as your logic only sets the
   TTL when the returned value tells you this was the first increment (a
   brief window where the key exists without a TTL is a minor cosmetic
   issue, not a correctness one, for this specific pattern -- but a Lua
   script closes even that gap and is the more defensible answer to write
   up in NOTES.md).

Now the two-tier structure. Rate and quota are independent caps on
different timescales, so give them **separate keys with separate TTLs** --
don't try to encode both in one counter. Something like one key family
namespaced for the rate window and another for the quota window, both
under `REDIS_PREFIX`, both per `api_key`. Each gets its own atomic
check-and-increment; the overall decision is "reject if either fires,"
with the two checks composed so that a rejection from one never mutates
the other's counter (see hint 3 for the ordering that makes this work
without extra bookkeeping).
