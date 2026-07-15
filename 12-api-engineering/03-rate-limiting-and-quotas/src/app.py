"""s12.t03 -- Redis-backed rate limiting and quotas for a public API.

The marketplace search endpoint is public and getting scraped abusively.
The fix is a per-API-key limiter backed by Redis:

  - a short-window RATE limit (burst protection): at most RATE_LIMIT
    requests per RATE_WINDOW_SEC, per key;
  - a longer-window QUOTA (sustained cap): at most QUOTA_LIMIT requests
    per QUOTA_WINDOW_SEC, per key.

When either is exceeded the endpoint returns HTTP 429 with a `Retry-After`
header and a body that says WHICH limit tripped.

The engineering that actually matters here is ATOMICITY. A naive
"read the counter, check it, then increment it" limiter has a race: under
concurrency, N requests can all read the same under-the-limit value before
any of them increments, and all N slip through -- so a limit of M lets
far more than M pass. The check-and-increment must be atomic (a single
Redis round trip / Lua EVAL), so that when many requests for one fresh key
arrive at once, EXACTLY RATE_LIMIT are allowed and the rest get 429.

You pick the window algorithm (fixed window / sliding-window log /
token bucket) and defend the choice in NOTES.md. Whatever you pick, a burst
of requests against a fresh key must admit EXACTLY RATE_LIMIT of them -- the
validator asserts that precisely.

Everything you write to Redis MUST be namespaced under REDIS_PREFIX
(`s12:t03:`) -- the Redis instance is shared with every other task in this
module. The constants below are imported by the validator, so it and your
app always agree on the limits; do not hardcode different numbers in your
handler.
"""

import os

from fastapi import FastAPI, Header

# --- Limiter configuration (the validator imports these names) --------------
# Small numbers on purpose so the validator runs in a few seconds. RATE is the
# tight short-window burst cap; QUOTA is the higher cap over a longer window.
RATE_LIMIT = 10
RATE_WINDOW_SEC = 2
QUOTA_LIMIT = 15
QUOTA_WINDOW_SEC = 20

# Every Redis key this task writes lives under this prefix. Never FLUSHALL --
# cleanup is redis_flush_prefix(client, REDIS_PREFIX) only.
REDIS_PREFIX = "s12:t03:"


def redis_url() -> str:
    """Async Redis URL for module 12's Redis (host port 6312 by default).
    Provided as boilerplate -- wiring the connection is not the exercise."""
    host = os.environ.get("PGHOST", "localhost")
    port = int(os.environ.get("SANDBOX_12_REDIS_PORT", "6312"))
    return f"redis://{host}:{port}/0"


app = FastAPI(title="s12.t03 rate-limited marketplace search")


class LimitDecision:
    """Result of one limiter check.

    allowed:     True if the request may proceed.
    which:       None when allowed; "rate" or "quota" when rejected.
    retry_after: whole seconds until the offending window frees up (the
                 counter's TTL) -- used for the Retry-After header.
    """

    def __init__(self, allowed: bool, which: str | None, retry_after: int):
        self.allowed = allowed
        self.which = which
        self.retry_after = retry_after


async def check_and_consume(api_key: str) -> LimitDecision:
    """Atomically check + increment BOTH the rate counter and the quota
    counter for `api_key`, and return a LimitDecision.

    Requirements:
      - Rate: allow at most RATE_LIMIT requests per RATE_WINDOW_SEC per key.
      - Quota: allow at most QUOTA_LIMIT requests per QUOTA_WINDOW_SEC per key.
      - ATOMIC check-and-increment (one Redis round trip / Lua EVAL) so that
        a concurrent burst against a fresh key admits EXACTLY RATE_LIMIT.
        A GET-then-INCR in two round trips is a race -- see the hints.
      - All keys under REDIS_PREFIX.
      - A request rejected by the rate limit must NOT consume quota budget.
      - On rejection set retry_after to the offending counter's TTL (seconds).
    """
    raise NotImplementedError


@app.get("/search")
async def search(q: str = "", x_api_key: str = Header(...)):
    """Rate-limited + quota-limited marketplace search.

    On each request:
      1. Call check_and_consume(x_api_key).
      2. If rejected, return HTTP 429 with a `Retry-After` header (whole
         seconds) and a JSON body whose `error` field distinguishes the two
         cases: "rate_limited" vs "quota_exceeded".
      3. If allowed, run a trivial read-only `shop` query for `q` (e.g. a
         title ILIKE match, LIMIT a few rows) and return the matches. The
         payload is deliberately not the point of this task -- the limiter
         is -- so keep it minimal.
    """
    raise NotImplementedError
