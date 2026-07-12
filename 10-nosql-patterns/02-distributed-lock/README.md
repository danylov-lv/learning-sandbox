# 02 -- Distributed Lock

## Backstory

Your scraper fleet has multiple workers, and every so often two of them pick
up the same domain at the same moment -- both start hitting the same shop,
double the load, double the risk of getting banned, and duplicate work for no
reason. You only want ONE worker processing a given resource (a domain, a
product, whatever the unit of work is) at a time, across the whole fleet, not
just within one process. That's what a distributed lock is for: a piece of
shared state (in Redis, here) that says "worker X holds resource Y until
time T," which every worker checks before touching that resource.

The dangerous part isn't acquiring the lock -- `SET key token NX PX ttl` does
that atomically in one round trip. The dangerous part is everything after:
what happens when a worker releases the lock, and what happens when a
worker's lock TTL expires while the worker is still alive and still working
(a slow disk write, a GC pause, a scheduler hiccup -- anything that stalls a
thread past the TTL). A worker that releases with a plain `DEL key` doesn't
know WHOSE lock is currently sitting in that key. If its own TTL already
expired and a second worker legitimately acquired the lock in the meantime,
that innocent-looking `DEL` deletes the SECOND worker's active lock -- now a
third worker can jump in while the second worker still thinks it's exclusive,
and you've got two, or three, workers stomping on the same resource at once.
This is the canonical distributed-lock footgun, and it's the specific bug this
task makes you reproduce and then fix.

Fixing release doesn't fully fix the underlying problem, though. Even a
perfectly safe release can't stop a worker that stalled past its TTL from
resuming later and acting as if it still holds the lock -- Redis has already
handed the lock to somebody else by then, and the stalled worker has no way to
find out short of asking Redis again (which it isn't doing, because it thinks
it doesn't need to). That's what a fencing token is for: a number that only
ever goes up, handed out at acquire time, that a downstream resource (a
database row, a file, an object store) can use to reject a write that arrives
out of order -- even from a worker Redis itself no longer knows is confused.

## What's given

- `src/lock.py` -- a `Lease` type and a `RedisLock` class scaffold. Rich
  docstrings on `acquire()` and `release()` explain exactly what each must do
  and why. Both currently `raise NotImplementedError`.
- The live stack: Redis on `localhost:6310` (`SANDBOX_10_REDIS_PORT`), no
  password. `harness/common.py` gives you `redis_client()`,
  `redis_flush_prefix()`, and `run_concurrently()` (a thread-pool helper for
  hammering the lock from multiple workers at once).
- `namespace="s10:t02:"` -- every Redis key this task touches must live under
  this prefix, per the module's shared-stack namespacing convention (see the
  module README). The validator resets this prefix before running.

## What's required

Implement `RedisLock` in `src/lock.py`:

1. **`acquire(self, ttl_ms: int) -> Optional[Lease]`** -- attempt to take the
   lock ONCE (no internal retry loop; retrying with backoff is the caller's
   job). Use `SET <lock key> <token> NX PX <ttl_ms>` so the check-and-set is
   atomic on Redis's side. `token` must be a fresh, globally-unique value
   generated on every call (not derived from the thread or hostname alone --
   two different acquisitions, even by the same worker, must never be able to
   produce the same token). On success, mint a fencing number by `INCR`-ing a
   persistent counter key and return a `Lease(token, fence)`. On failure
   (someone else already holds the lock), return `None`.
2. **`release(self, lease: Lease) -> bool`** -- release the lock, but ONLY if
   it is still `lease`'s lock. This must be a single atomic
   compare-and-delete on Redis's side (a Lua script is the standard tool: read
   the key's current value and delete it only if it still equals
   `lease.token`, all inside one `EVAL`). A client-side `GET` followed by a
   separate `DEL` is NOT safe, no matter how fast it looks -- there is a gap
   between the two calls, and if the lock expired and a different worker
   acquired it inside that gap, the `DEL` deletes the wrong worker's lock.
   Return `True` iff this call actually deleted its own lock, `False`
   otherwise (lease already expired / already released / never held).

All keys this class touches must live under `namespace` (default
`s10:t02:`).

Try it by hand before trusting the validator: open a Python shell (`uv run
python` from `10-nosql-patterns/`), construct a `RedisLock`, and walk through
acquire / release yourself, including letting a short TTL expire and watching
what a second acquire does to the key.

## Completion criteria

Run, from this task's directory:

```bash
uv run python tests/validate.py
```

It:

- **Mutual exclusion under concurrency.** Several threads spin-acquire the
  SAME lock in a loop, each doing a deliberately racy read-modify-write on a
  shared Python counter inside the critical section (read, sleep a
  millisecond, write) before releasing. With a correct lock, the final counter
  equals `n_workers * iters` EXACTLY -- no update is ever lost. A lock that
  isn't truly exclusive loses updates, and the validator checks for an EXACT
  match, not "close enough".
- **Safe release (the wrong-owner bug).** Acquires lease A with a short TTL,
  lets it expire, acquires lease B (a different token), and asserts that
  `release(leaseA)` returns `False` AND that the lock key still holds lease
  B's token afterward -- proving the release didn't blow away a lock it no
  longer owns. Then asserts `release(leaseB)` returns `True`.
- **Fencing monotonicity.** Several successive successful acquires of the
  same resource must yield strictly increasing `.fence` values.
- Prints `PASSED` with the observed counter value, or `NOT PASSED: <reason>`
  and exits 1 on any failure -- including the stack being down or a method
  still raising `NotImplementedError`.

## Estimated evenings

1-2

## Topics to read up on

- `SET key value NX PX ttl` -- why combining existence-check, value-set, and
  expiry into one command is what makes acquire atomic
- Atomic compare-and-delete via a Redis Lua script (`EVAL`) -- why Redis
  running the script as one server-side unit closes the race a client-side
  GET-then-DEL cannot
- Lock TTL as a safety/liveness trade-off: too long and a crashed worker's
  lock outlives it and blocks everyone; too short and a slow-but-alive worker
  can lose its lock mid-task
- Fencing tokens -- why a TTL-based lock alone is not enough to guarantee
  mutual exclusion at the downstream resource, and how a monotonically
  increasing token handed to that resource closes the gap
- Unique lock ownership tokens -- why the value stored in the lock key must
  identify a specific acquisition, not just a specific worker

## Off-limits

`.authoring/` (at the module root) holds the full data contract, RNG draw
order, and design rationale for every task in this module -- spoilers. This
task doesn't use the module's product/event data at all, but the file is
off-limits regardless.
