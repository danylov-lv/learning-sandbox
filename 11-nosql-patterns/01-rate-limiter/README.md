# 01 -- Rate Limiter

## Backstory

Your scraper runs many worker processes in parallel, all hitting the same
handful of domains. Every domain enforces (or you've promised yourself to
respect) a cap: no more than `limit` requests per `window_seconds`, per
domain. Exceed it and you get throttled, banned, or you've simply been a bad
citizen of someone else's infrastructure.

The obvious first implementation is "look up how many requests this domain
has made recently, and if it's under the limit, record one more":

```
count = get_count(domain)
if count < limit:
    increment_count(domain)
    allow()
else:
    reject()
```

This is a **check-then-act** race. Between the read and the write, any
number of other workers can run the exact same check against the exact same
pre-update count, and all decide to admit. With enough concurrent workers
you don't cap the domain at `limit` requests per window -- you blow past it,
sometimes by a lot, exactly when you most need the cap to hold (a burst of
workers all starting up at once). The fix isn't a bigger lock around the
whole check -- it's making Redis do the check-and-record as a single atomic
operation, so no interleaving is possible.

## What's given

- `src/limiter.py` -- a `RateLimiter` class scaffold. `__init__` takes a
  Redis client, a `limit`, a `window_seconds`, and a `namespace`. The one
  method you implement, `allow(resource)`, currently `raise
  NotImplementedError`. The docstrings spell out exactly what atomicity
  guarantee is required and why check-then-act fails it.
- The live stack: Redis on `localhost:6310` (see `harness/common.py` for
  `redis_client()`), already running via `docker compose up`.
- `harness/common.py`'s `redis_flush_prefix` (reset your namespace before a
  run) and `run_concurrently` (fire many concurrent calls across threads and
  collect results in a deterministic order) -- both used by the validator,
  and both fair game to use yourself while poking at your implementation by
  hand.

## What's required

Implement `RateLimiter.allow(self, resource: str) -> bool` in
`src/limiter.py` so that:

1. It **atomically** records a hit against `resource` and decides
   admission -- no separate read-then-write that another caller's call
   could interleave with.
2. Under concurrent callers hammering the same `resource`, **exactly**
   `limit` calls are admitted per window -- not more (over-admission from a
   race), not fewer (under-admission from counting rejected calls against
   the budget, or some other bug).
3. Different `resource` values have **fully independent** budgets.
4. Once `window_seconds` has elapsed, the budget for a resource becomes
   available again.
5. Every Redis key you touch lives under `self.namespace` (default
   `s10:t01:`) -- the Redis instance is shared across every task in this
   module.

You have real design freedom here: a fixed window (INCR + EXPIRE on first
hit), a sliding-window log (a sorted set of hit timestamps), and a token
bucket are all valid strategies, each with different tradeoffs (see hints
if you want a nudge). Whichever you pick, the validator only checks
observable behavior, not which strategy you used.

## Completion criteria

Run, from this task's directory:

```bash
uv run python tests/validate.py
```

It:

- Resets the `s10:t01:` namespace, then fires many concurrent `allow()`
  calls against one resource with a long window and a limit `L`, and
  asserts the number of admitted (`True`) calls is exactly `L` -- neither
  more (a race let extras through) nor fewer (a bug ate legitimate budget).
- Asserts two different resources have independent budgets: exhausting one
  does not affect the other.
- Exhausts a resource's budget under a short window, sleeps past the
  window, and asserts the budget is available again.
- Prints a `PASSED` message with the observed admitted-call count, or
  `NOT PASSED: <reason>` and exits 1 on any failure -- including the stub
  still raising `NotImplementedError` or the stack being unreachable.

## Estimated evenings

1

## Topics to read up on

- Atomic Redis operations, and what "atomic" actually buys you
- Lua scripting with `EVAL` (how Redis runs a script to completion without
  interleaving other clients' commands)
- Fixed-window vs sliding-window-log vs token-bucket rate limiting
- Check-then-act race conditions
- `INCR` / `EXPIRE`
- Sorted sets: `ZADD` / `ZREMRANGEBYSCORE` / `ZCARD`

## Off-limits

`.authoring/` (at the module root) holds the full data contract, RNG draw
order, and the shared Redis/Mongo/Postgres namespacing convention for every
task in this module -- spoilers. Don't read it before finishing this task.
