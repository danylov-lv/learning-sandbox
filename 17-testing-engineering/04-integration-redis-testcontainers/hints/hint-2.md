# Hint 2 -- naming the mechanisms

Five distinct things need at least one test each. For each, here is the
Redis-level mechanism that lets you observe it without guessing or
sleeping through it:

- **Boundary correctness.** Call `allow()` in a loop against one fresh key
  with a small `limit` (e.g. 3) and record every return value. The first
  `limit` calls must be `True`, and the very next one `False`. Off-by-one
  bugs (admitting `limit + 1`, or denying the `limit`-th call) only show
  up if you check the *exact* count, not just "eventually it returns
  False."

- **TTL is actually set.** After any call that writes a key, ask Redis
  directly: `redis_client.ttl(the_key)` (seconds) or `.pttl(the_key)`
  (milliseconds). Both return a negative number if the key has no expiry
  or doesn't exist. A leaked key is a key with no TTL -- that is a
  first-class thing to assert, not an implementation detail to ignore. You
  will need to know (or reconstruct) the exact key name the component
  writes -- look at how `impl.py` builds it from the prefix and your
  input key.

- **The window doesn't get pushed back by later calls.** Read the TTL
  right after the call that opens a window, wait a short moment (well
  under a second), make another call against the same key, and read the
  TTL again. If the implementation is correct, the second reading is
  *lower* than the first by roughly the wait time. If something resets the
  expiry on every call, the second reading jumps back up near the full
  window instead of continuing to count down.

- **The window actually resets.** You do not need to sleep for the whole
  `window_seconds` to prove this. Redis lets you rewrite a key's TTL
  directly: `redis_client.pexpire(the_key, 50)` forces near-immediate
  expiry regardless of what window you originally asked for. Force it low,
  wait a short moment for it to actually expire, then call `allow()` again
  and check it behaves like a fresh key.

- **Namespace isolation and dedup correctness** are both about calling the
  two components (or two instances of the same one) side by side against
  the same or different key strings and checking neither's state leaks
  into the other's, and that `seen()` returns `False` then `True` for
  repeat calls on one key within its TTL.
