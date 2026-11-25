# 02 -- Response Caching with Redis

## Backstory

The marketplace's category pages show a little summary box: how many products
are in the category, their total value, and the average price. It is computed
by an aggregation over `shop.products` -- a `count` + `sum` + `avg` filtered
by `category_id`. For a small category that's cheap; for "Headphones & Audio"
(52,000+ products) it is not, and every single page view recomputes it from
scratch.

On a quiet laptop the endpoint looks fine. Put it behind a homepage that
links to the top categories and the same handful of aggregations run over and
over, thousands of times a minute, each one an identical scan Postgres has
already answered moments ago. The database is doing the same expensive work
repeatedly to produce a number that barely changes.

The fix is a cache in front of the expensive query: **cache-aside**. Check
Redis first; on a miss, compute from Postgres and store the result with a
short TTL; on a hit, serve straight from Redis and never touch Postgres. Add
an explicit invalidation path so that when a product in the category changes,
you can drop the stale entry on demand instead of waiting for the TTL.

The catch: a cache is only worth having if it stays **correct**. A fast wrong
answer is worse than a slow right one. The validator computes its own summary
straight from `shop` and refuses to trust yours -- your cached path has to be
both dramatically faster AND byte-for-byte correct.

## What's given

- `src/app.py` -- a real FastAPI `app` with both routes defined and their
  handler bodies stubbed as `raise NotImplementedError`. The cache key prefix
  (`CACHE_PREFIX = "s12:t02:summary:"`) and TTL (`CACHE_TTL_SECONDS = 60`) are
  fixed constants; you fill in the two bodies.
- `baseline.py` -- launches your app and measures MISS vs HIT latency on this
  machine, writing `caching-local.json` (gitignored). Run it once after you
  implement the app.
- `tests/validate.py` -- the checker (see Completion criteria).
- The shared harness (`harness.common`, `harness.service`): `pg_conn()` /
  `pg_pool()` for Postgres, `redis_client()` for Redis, `run_app()` to launch
  the app on an ephemeral port. Use them or your own clients -- only the
  observable contract is graded.
- A seeded, read-only `shop` schema (Postgres on port 54312) and a shared
  Redis (port 6312). Both are already running.

## What's required

Implement the two handlers in `src/app.py`:

### `GET /categories/{category_id}/summary`

Returns JSON `{"category_id", "product_count", "price_sum", "avg_price"}` for
the leaf category, where `product_count` is the number of `shop.products`
rows in it, `price_sum` their total price, and `avg_price` the mean.

- **On a cache MISS** (no entry in Redis): compute the summary from Postgres,
  store it in Redis under the key `CACHE_PREFIX + str(category_id)` (i.e.
  `s12:t02:summary:<id>`) with a `CACHE_TTL_SECONDS` TTL, set the response
  header `X-Cache: MISS`, and return it.
- **On a cache HIT** (entry present): return the cached value WITHOUT querying
  Postgres, set the response header `X-Cache: HIT`. The HIT response body must
  be **byte-for-byte identical** to the MISS body that populated the cache --
  serve the stored bytes, do not recompute or re-serialize into a different
  shape. Building a `fastapi.Response` from the exact stored payload is the
  clean way to guarantee this.

### `POST /categories/{category_id}/invalidate`

Deletes the cached entry (the Redis key `CACHE_PREFIX + str(category_id)`) so
the next GET is a MISS again, and returns HTTP 200 -- whether or not a key was
actually there. This simulates "a product in this category changed, drop the
stale summary."

### The `X-Cache` header contract

The header is how the validator (and any client, and you) can tell whether a
response came from Postgres or Redis without inspecting timings:

| Situation                                   | `X-Cache` |
|---------------------------------------------|-----------|
| computed from Postgres, just cached          | `MISS`    |
| served from an existing Redis entry          | `HIT`     |

### Redis namespacing rule (module-wide, non-negotiable)

Every Redis key this task writes MUST start with `s12:t02:`. The Redis
instance is shared with every other task's validator running in parallel, so
you clean up ONLY your own prefix (the harness helper `redis_flush_prefix`
does this) and **never** call `FLUSHALL` / `FLUSHDB`.

## Completion criteria

Run, from this task's directory:

```bash
uv run python baseline.py        # once -- writes the machine-local timing baseline
uv run python tests/validate.py
```

The validator:

- Launches your app; a stub handler (HTTP 500) yields a single-line
  `NOT PASSED`.
- Checks **correctness** for several leaf categories against its own oracle
  computed straight from `shop.products` (count / sum / avg, with float
  tolerance) -- never trusting your app's numbers.
- Checks the **cache engages**: the first GET reports `X-Cache: MISS` and
  creates `s12:t02:summary:<id>`; the second reports `X-Cache: HIT` with the
  key still present.
- Checks **invalidation**: after `POST .../invalidate` the key is gone and the
  next GET is a MISS again.
- Checks **cache fidelity**: the HIT body equals the MISS body byte-for-byte.
- Checks a **relative speedup**: reads `caching-local.json` and asserts the
  HIT path is materially faster than the MISS path on this machine (never an
  absolute millisecond number). A missing baseline is a `NOT PASSED` telling
  you to run `baseline.py`.

It prints `PASSED` with the category count and observed speedup, or
`NOT PASSED: <reason>` and exits 1.

## Estimated evenings

1

## Topics to read up on

- Cache-aside (lazy loading) vs read-through / write-through caching
- TTL and cache invalidation (the "two hard things" problem)
- Cache key design and namespacing
- Serialization of cached payloads (what exactly you store and return)
- Thundering herd / cache stampede -- what happens when a hot key expires
  under load and many requests miss at once (an open question here: this
  task's simple cache-aside does NOT solve it; think about how you would)

## Off-limits

`.authoring/design.md` (at the module root) documents the harness API, the
`shop` schema, the committed ground truth, and the verification philosophy for
every task in this module -- spoilers. Don't read it before finishing.
