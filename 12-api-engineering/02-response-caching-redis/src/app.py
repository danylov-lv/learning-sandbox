"""s12.t02 -- response caching with Redis (cache-aside).

One endpoint runs an expensive per-category aggregation over `shop.products`
(count + price sum + average price for a leaf category). Under load, every
request recomputes the same aggregate and hammers Postgres with identical
scans. The fix is a cache-aside layer in Redis: check the cache first, only
touch Postgres on a miss, store the computed result with a TTL, and expose an
explicit invalidation path so a stale entry can be dropped on demand.

A cache is only worth having if it stays CORRECT -- a fast wrong answer is
worse than a slow right one. The validator computes its OWN oracle straight
from `shop` and refuses to trust this app's numbers.

You implement the two handler bodies below. Everything else -- the `app`
object, the routes, the cache key prefix, the TTL, and the `X-Cache` header
contract -- is fixed by the scaffold and the README so the validator can
observe the behavior it needs to.

Reaching Postgres and Redis: `harness.common` gives you `pg_conn()` /
`pg_pool()` and `redis_client()` (the module root is on `sys.path` when this
app is launched by the validator or `baseline.py`). You may use those or your
own clients -- the validator only cares about the observable contract, not
how you connect.

Contract the validator depends on (see README for the full description):

- `GET /categories/{category_id}/summary` returns JSON
  `{"category_id", "product_count", "price_sum", "avg_price"}` for that leaf
  category, and sets a response header `X-Cache: MISS` when the value was
  just computed from Postgres, or `X-Cache: HIT` when it was served from
  Redis without touching Postgres.
- The cached entry lives at the Redis key `CACHE_PREFIX + str(category_id)`
  (i.e. `s12:t02:summary:<id>`) and expires after `CACHE_TTL_SECONDS`.
- On a HIT, the response body must be byte-for-byte identical to the body
  that was served on the MISS that populated the cache -- serve the cached
  bytes, do not recompute or re-serialize into a different shape. (Returning
  a `fastapi.Response` built from the exact stored payload is the clean way
  to get this.)
- `POST /categories/{category_id}/invalidate` deletes the cached entry and
  returns HTTP 200, so the next GET is a MISS again.

Redis namespacing rule (module-wide, non-negotiable): every key this task
writes MUST start with `s12:t02:`. Never call FLUSHALL/FLUSHDB -- other
tasks' validators share this Redis instance.
"""

from fastapi import FastAPI, Response  # noqa: F401  (Response is the clean way to control body+headers)

CACHE_PREFIX = "s12:t02:summary:"
CACHE_TTL_SECONDS = 60

app = FastAPI(title="s12.t02 response caching")


@app.get("/categories/{category_id}/summary")
async def category_summary(category_id: int, response: Response):
    """Return the cached aggregate for `category_id`, computing it from
    Postgres only on a cache miss.

    On MISS: compute `{"category_id", "product_count", "price_sum",
    "avg_price"}` from `shop.products` for this category, store it in Redis
    under `CACHE_PREFIX + str(category_id)` with a `CACHE_TTL_SECONDS` TTL,
    signal `X-Cache: MISS`, and return it.

    On HIT (key present in Redis): return the cached body unchanged WITHOUT
    querying Postgres, signalling `X-Cache: HIT`. The returned bytes must
    match the MISS body exactly.

    `product_count` is the number of `shop.products` rows in the category,
    `price_sum` their total price, and `avg_price` the mean price (define a
    sensible value -- e.g. null -- for an empty category; the validator only
    checks non-empty leaf categories).
    """
    raise NotImplementedError


@app.post("/categories/{category_id}/invalidate")
async def invalidate_category(category_id: int):
    """Delete the cached summary for `category_id` (the Redis key
    `CACHE_PREFIX + str(category_id)`) so the next GET recomputes from
    Postgres. Return HTTP 200 whether or not a key was actually present."""
    raise NotImplementedError
