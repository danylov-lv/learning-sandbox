"""s10.t01 -- an atomic, concurrency-correct rate limiter in Redis.

Scraper workers throttle requests to a domain: no more than `limit` requests
per `window_seconds`, shared across every worker process that imports this
class. The naive approach --

    count = client.get(key)
    if count is None or int(count) < limit:
        client.incr(key)
        return True
    return False

-- is a classic check-then-act race. Between the GET and the INCR, any
number of other threads/processes can run the same GET, see the same
under-the-limit count, and also decide to admit. Redis executes each of
GET and INCR atomically, but the *pair* of them is not atomic: nothing stops
another client's GET from being interleaved between your GET and your INCR.
Under concurrency this over-admits -- N callers can race past a limit of 1.
Fire enough concurrent callers at a limit of 50 with a naive check-then-act
limiter and you will observe well over 50 admissions, not exactly 50.

The fix is to make "check and record" a single atomic operation from Redis's
point of view -- either one command that does both (Redis's own INCR already
returns the post-increment value, so INCR-then-compare needs no separate
GET), or a small Lua script executed via EVAL, which Redis runs to
completion without interleaving any other client's commands in between.

This module defines the scaffold. Implement `RateLimiter.allow()` so that,
under concurrent callers hammering the same resource, EXACTLY `limit` calls
return True per window -- no more (over-admission), no fewer
(under-admission).
"""


class RateLimiter:
    """A rate limiter keyed by an arbitrary resource string (e.g. a domain),
    backed by Redis, confined to `namespace`.

    All keys this limiter touches MUST live under `self.namespace` (default
    `s10:t01:`) -- the Redis instance is shared across every task in this
    module, and validators reset only their own task's prefix.
    """

    def __init__(self, client, *, limit: int, window_seconds: float, namespace: str = "s10:t01:"):
        """
        Args:
            client: a connected `redis.Redis` (see `harness.common.redis_client`).
            limit: max number of admitted (True-returning) `allow()` calls
                per `resource` per window.
            window_seconds: window length in seconds. May be fractional.
                Both a fixed-window and a sliding-window-log implementation
                are valid strategies -- pick one and be consistent about
                what "per window" means for it (see hints if unsure which
                to reach for).
            namespace: key prefix every Redis key this instance touches must
                start with. Do not hardcode "s10:t01:" inside `allow()` --
                read it from `self.namespace` so the default can be
                overridden (e.g. by tests wanting a scratch prefix).
        """
        self.client = client
        self.limit = limit
        self.window_seconds = window_seconds
        self.namespace = namespace

    def allow(self, resource: str) -> bool:
        """Atomically record one hit against `resource` and report whether
        it falls within the limit for the current window.

        Must return True for the FIRST `limit` calls made against a given
        `resource` within a window, and False for every call beyond that,
        even when many callers invoke this concurrently from different
        threads or processes. The read (how many hits so far) and the write
        (record this hit) must happen as one atomic unit as far as Redis is
        concerned -- a separate GET-then-INCR-if-under-limit is NOT
        sufficient, because two concurrent callers can both read the same
        pre-increment count and both decide to admit, pushing the true
        admitted count above `limit` (over-admission). Conversely, don't
        record a hit for a call you're about to reject -- that would
        under-admit by permanently consuming budget for a rejected request.

        Different `resource` values must have fully independent budgets:
        exhausting the budget for one resource must not affect any other.
        Every key this method touches must be namespaced under
        `self.namespace` plus something derived from `resource` (e.g.
        `self.namespace + resource`), never a bare `resource` string --
        otherwise two tasks' rate limiters could collide on the shared
        Redis instance.

        Args:
            resource: the thing being rate-limited (e.g. a domain like
                "shop.example"). Treat it as an opaque string.

        Returns:
            True if this call is admitted (within the limit for the
            current window), False if the caller should back off.
        """
        raise NotImplementedError
