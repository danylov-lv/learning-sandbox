# 04 -- Integration Testing: Redis Testcontainers

## Backstory

The scraper's request pipeline leans on Redis for two small but
load-bearing jobs: a fixed-window rate limiter that keeps any one
target/key from being hammered too fast, and a dedup filter that stops the
same URL from being reprocessed while it is still "fresh" in the queue.
Both are simple in principle -- an increment, a TTL, a conditional set --
and both are exactly the kind of code that looks obviously correct on a
read-through and then quietly breaks in production: a TTL that never got
attached leaks a key forever, a check-then-set that isn't atomic lets one
extra request slip past a boundary, a copy-pasted key format collides two
things that were supposed to be independent. A unit test against a fake or
mocked Redis client will not catch most of these -- it tests your mock's
behavior, not Redis's actual atomicity and expiry semantics. The only way
to trust this code is to run it against a real Redis.

## What's given

- `src/impl.py` -- a correct, already-atomic `RateLimiter` (fixed-window,
  via a Lua `EVAL` doing `INCR` + `EXPIRE` in one round trip) and
  `DedupFilter` (`SET ... NX EX` in one round trip), both backed by a
  `redis-py` client and both namespacing their keys under a prefix. Read
  it, do not edit it -- it is not the deliverable, your test suite is.
- `src/sut.py` -- a generated shim; your tests import `RateLimiter` /
  `DedupFilter` from here (`from src.sut import RateLimiter, DedupFilter`),
  never from `src.impl` directly.
- `tests/conftest.py` -- a session-scoped `RedisContainer("redis:7")`
  fixture (`redis_client`) and an autouse fixture that flushes the
  container's keyspace before every test. This is scaffolding, not the
  deliverable; you should not need to edit it.
- `tests/test_redis_component.py` -- a stub with no tests yet. This is
  where your work goes.
- **Docker Desktop must be running.** This task starts a real, ephemeral
  Redis container per `pytest` run.

## What's required

Write `tests/test_redis_component.py` so it exercises `RateLimiter` and
`DedupFilter` against the real container thoroughly enough to catch a
regression in any of:

- The rate-limit boundary (exactly `limit` calls admitted, the next
  denied -- not `limit - 1`, not `limit + 1`).
- TTL actually being set on every key either component writes (a key with
  no TTL is a leak, not a passing test).
- The window not being pushed back out by calls that happen after it
  already opened (only the call that *opens* a window sets its TTL).
- The window genuinely resetting once its TTL has elapsed (verify this via
  a short window or by manipulating the key's TTL directly -- do not rely
  on wall-clock sleeps longer than about a second, that is slow and
  flaky).
- Key namespace isolation, so two different keys -- or a limiter and a
  filter fed the same logical key string -- never share state.
- Dedup correctness: the first `seen(key)` is `False`, a second call for
  the same key within the TTL is `True`.

`impl.py` is correct and off-limits to editing. `.authoring/` (at the
module root) is off-limits to reading before you finish -- it holds the
mutant bank your suite is graded against, which is exactly the answer key.

## Completion criteria

From this task's directory:

```bash
uv run python tests/validate.py
```

This runs your suite against the real, correct implementation (it must
pass, and must collect a handful of real tests) and then, one at a time in
fresh subprocesses, against a bank of mutated implementations, each with
exactly one planted bug. Your suite must fail against every mutant. Prints
`PASSED` with a kill count, or `NOT PASSED: <reason>` (including which
mutants survived, by filename only) and exits 1. Requires Docker; each
mutant run starts its own fresh container, so a full run takes a while --
that is expected.

## Estimated evenings

2

## Topics to read up on

- `testcontainers` for Redis (session- vs function-scoped fixtures,
  container lifecycle cost)
- Atomic Redis operations: Lua `EVAL`, `MULTI`/`EXEC` pipelines, and why
  `GET` then `SET` across two round trips is not the same thing
- Fixed-window rate limiting and its boundary semantics
- Redis key TTL/expiry semantics (`EXPIRE`, `TTL`, `PTTL`, `PEXPIRE`, `SET
  ... NX EX`)
- Key namespacing / prefixing conventions for shared Redis instances
- Testing time-dependent behavior without flaky wall-clock sleeps

## Off-limits

`.authoring/design.md` (at the module root) holds the harness API
contract and the mutant bank's design notes for every task in this
module -- spoilers. Don't read it before finishing this task.
