# 03 -- Rate Limiting and Quotas

## Backstory

The marketplace search API is public, and it is being scraped. A handful of
API keys are hammering `GET /search` thousands of times a minute -- driving
up database load and crowding out real users. The product decision is to keep
the endpoint public but put a limiter in front of it: every caller sends an
API key, and each key gets a fair, bounded slice of capacity.

Two limits, on two timescales:

- A **rate limit** for burst protection -- at most `RATE_LIMIT` requests per
  `RATE_WINDOW_SEC`, per key. This stops a single key from firing a thousand
  requests in one second.
- A **quota** for sustained use -- at most `QUOTA_LIMIT` requests per
  `QUOTA_WINDOW_SEC` (a longer window), per key. This is the "daily cap"
  shape: even a well-behaved caller that never trips the rate limit still
  can't consume unlimited total capacity.

When a caller exceeds either, the API returns **HTTP 429** with a
`Retry-After` header, and a body that says WHICH limit tripped.

The limiter lives in Redis because the API runs as multiple stateless
workers -- an in-process counter would let a key get `RATE_LIMIT` requests
*per worker*. The counters have to be shared, and that is where the real
engineering is: doing the check-and-increment **atomically**. A naive
"read the counter, see it's under the limit, then increment it" has a race.
Under concurrency, many requests read the same under-the-limit value before
any of them writes back, and they all slip through -- so a limit of `M` lets
far more than `M` pass exactly when you need it most (an abusive client
sending everything at once). Fixing that race is the point of this task.

## What's given

- `src/app.py` -- a FastAPI `app` with a `GET /search` route and a
  `check_and_consume(api_key)` limiter function, both defined but raising
  `NotImplementedError`. The limiter constants (`RATE_LIMIT`,
  `RATE_WINDOW_SEC`, `QUOTA_LIMIT`, `QUOTA_WINDOW_SEC`, `REDIS_PREFIX`) are
  module-level names -- **the validator imports them**, so you and it always
  agree on the numbers. A `redis_url()` helper is provided as boilerplate.
- The shared, read-only `shop` corpus in Postgres for the trivial search
  payload (the payload is not the point; the limiter is).
- The module harness: `harness/service.py` (`run_app`, `asgi_client`),
  `harness/load.py` (`bombard`), `harness/common.py`
  (`redis_client`, `redis_flush_prefix`, ...).

## What's required

Implement `check_and_consume` and the `/search` handler so that:

1. **Algorithm** -- pick one (fixed window / sliding-window log / token
   bucket) and defend it in `NOTES.md`. Whatever you pick, a burst of
   requests against a fresh key must admit **exactly `RATE_LIMIT`** of them.
2. **Atomic check-and-increment** -- one Redis round trip (a Lua `EVAL`, or
   an equivalently atomic construction). No GET-then-INCR across two round
   trips. Under a concurrent burst against a fresh key, exactly `RATE_LIMIT`
   requests get 200 and the rest get 429 -- never more than `RATE_LIMIT`.
3. **The status / header contract** -- on rejection, respond `429` with a
   `Retry-After` header (whole seconds until the offending window frees up)
   and a JSON body whose `error` field distinguishes the two cases:
   `"rate_limited"` vs `"quota_exceeded"`. A request rejected by the rate
   limit must not consume quota budget.
4. **Key isolation** -- counters are per key; one key hitting its limit must
   never affect another key's budget.
5. **The `s12:t03:` prefix** -- every Redis key you write is namespaced under
   `REDIS_PREFIX`. Never `FLUSHALL`/`FLUSHDB`; the Redis instance is shared
   with every other task in this module.

## Completion criteria

Run, from this task's directory:

```bash
uv run python tests/validate.py
```

It launches your app on an ephemeral port and checks: a fresh key admits
exactly `RATE_LIMIT` under the limit; the next request is `429` + `Retry-After`;
a **concurrent** burst of well more than `RATE_LIMIT` admits *exactly*
`RATE_LIMIT` (the atomicity test -- a racy limiter fails here); a second key
keeps its own budget; the window resets after `RATE_WINDOW_SEC`; and crossing
`QUOTA_LIMIT` yields a `429` whose body says quota, not rate. It prints
`PASSED` with the observed counts, or `NOT PASSED: <reason>` and exits 1
(including on the unimplemented stub). Redis keys under `s12:t03:` are flushed
on setup and teardown.

## Estimated evenings

1-2

## Topics to read up on

- Fixed window vs sliding window (log and counter) vs token bucket
- Atomic counters in Redis: `INCR` + `EXPIRE`-on-first, and Lua `EVAL`
  atomicity
- Check-then-set race conditions in a check-and-increment limiter
- `Retry-After` header semantics (429 / 503)
- Per-key quotas and multi-tier limiting (burst cap + sustained cap)
- Key TTLs and how a fixed window resets

## Off-limits

`.authoring/design.md` (at the module root) holds the harness API contract,
the corpus ground truth, and the verification philosophy behind every task in
this module -- spoilers. Don't read it before finishing this task.
