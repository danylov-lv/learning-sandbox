"""s10.t02 -- a correct distributed lock over Redis.

Acquiring a distributed lock is the easy part: `SET key token NX PX ttl` does
a check-and-set with an expiry attached, atomically, in one round trip. Every
interesting bug in this task lives in the two places that command doesn't
cover:

1. RELEASE. A worker must only ever delete a lock it currently holds. If its
   TTL already expired and a different worker has since acquired the same
   key, a plain `DEL` deletes THAT worker's lock -- the classic wrong-owner
   footgun described in the README. The fix is a release that is atomic
   compare-and-delete: check the key still holds THIS lease's token, and
   delete it, as one indivisible operation on Redis's side.

2. EXPIRY. Even a perfectly safe release cannot stop a worker that stalled
   (GC pause, slow disk, scheduler hiccup) longer than its TTL from resuming
   later and acting as if it's still exclusive -- Redis already gave the lock
   to somebody else by then, and the stalled worker has no way to find out on
   its own. A fencing token -- a number that only increases, handed out at
   acquire time -- lets a downstream resource reject a write that arrives out
   of order, closing the gap that TTL expiry alone leaves open.

`Lease` is what a successful `acquire()` hands back: enough information for
`release()` to prove ownership, and enough for a caller to pass a fencing
number downstream.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Lease:
    """What acquire() returns on success.

    token: a fresh, globally-unique string minted for THIS acquisition (not
        derived from worker identity alone -- the same worker acquiring twice
        must get two different tokens). This is what release() proves
        ownership with.
    fence: a monotonically increasing integer minted at acquire time, unique
        per acquisition of a given resource, strictly greater than every
        fence issued before it for that same resource. Meant to be handed to
        whatever downstream resource this lock is protecting, so that
        resource can reject a write whose fence is not the highest it has
        seen -- see the module docstring's point 2.
    """

    token: str
    fence: int


class RedisLock:
    """A mutual-exclusion lock over Redis for a single named resource.

    Two Redis keys are used per resource, both under `namespace`:

    - `self.lock_key`  -- holds the current holder's token while the lock is
      held; absent when the lock is free (either never taken, TTL-expired, or
      safely released).
    - `self.fence_key` -- a persistent counter, `INCR`-ed once per successful
      acquisition of this resource, never deleted. Its value never resets, so
      fences keep increasing across the resource's whole lifetime, including
      across expiries.

    One `RedisLock` instance is safe to share across threads/callers that all
    want to contend for the SAME resource: it holds no per-acquisition
    mutable state itself -- every acquisition's state lives in the `Lease` it
    returns and in Redis.
    """

    def __init__(self, client, key, *, namespace="s10:t02:"):
        self.client = client
        self.key = key
        self.namespace = namespace
        self.lock_key = f"{namespace}lock:{key}"
        self.fence_key = f"{namespace}fence:{key}"

    def acquire(self, ttl_ms: int) -> Optional[Lease]:
        """Attempt to take the lock ONCE. No retry loop in here -- a caller
        that wants to wait for a busy lock retries with its own backoff (see
        the validator for the shape of that).

        Required behavior:

        - Issue `SET self.lock_key <token> NX PX ttl_ms` where `<token>` is
          freshly generated for this call (e.g. a UUID) -- NX makes the
          "only if nobody holds it" check and the set happen as one atomic
          Redis operation, and PX attaches the expiry to that same command so
          there's no window where the key exists without a TTL. If the SET
          is rejected (key already present), the lock is held by someone
          else: return `None` immediately, and do NOT touch the fence
          counter.
        - If the SET succeeds, this call is now the holder. Obtain a fencing
          number for this acquisition via `INCR self.fence_key` (an integer
          that is guaranteed higher than every fence this resource has ever
          handed out, since INCR on a shared counter is atomic and the
          counter is never reset by a normal release).
        - Return `Lease(token=<the token you generated>, fence=<the INCR
          result>)`.

        Why the token must be unique per call, not per worker: `release()`
        proves ownership by checking the lock key still equals `lease.token`
        exactly. If two acquisitions (even from the same worker, e.g. a retry
        after its own lease expired) shared a token, `release()` could not
        tell them apart -- releasing the second, still-valid acquisition
        using a `Lease` object left over from the first, already-expired one
        would look like a legitimate release and silently drop a lock that's
        genuinely still needed.
        """
        raise NotImplementedError

    def release(self, lease: Lease) -> bool:
        """Release the lock -- but ONLY if it is still `lease`'s lock.

        Required behavior: perform an atomic compare-and-delete against
        `self.lock_key`, keyed on `lease.token`, as a single operation on
        Redis's side (a Lua script run via `EVAL`/a registered script is the
        standard way to do this: the script checks the key's current value
        against the token it was passed, and deletes the key only if they
        match, all inside Redis's single-threaded script execution -- nothing
        else can run between the check and the delete). Return `True` iff
        this call's compare-and-delete actually removed the key; return
        `False` if the key held a different token (or didn't exist at all).

        Why this cannot be a client-side `GET` followed by a separate `DEL`:
        those are two separate round trips. Between them, this lease's TTL
        could expire and a different worker could legitimately acquire the
        same lock -- and then this call's `DEL`, having already decided
        (from the stale `GET`) that it's safe to delete, would delete that
        OTHER worker's active lock instead of a no-op. That's the exact bug
        the "safe release" check in the validator reproduces and requires you
        to have fixed: `release()` on an expired, since-reacquired lease must
        return `False` and must leave the new holder's lock completely
        untouched.

        Note what this does NOT fix: a worker that stalls past its TTL and
        only resumes afterward can still believe it holds the lock even
        though this method (called by the CURRENT rightful holder, or never
        called at all by the stalled one) has nothing to do with that
        worker's stale belief. That gap is what the fencing token
        (`lease.fence`) is for -- pass it downstream and have the downstream
        resource reject stale writes, since a rejects-non-increasing-fence
        check downstream will always accept the later, higher-fenced holder
        and reject the earlier, lower-fenced one, regardless of what either
        one currently believes about its own lock.
        """
        raise NotImplementedError
