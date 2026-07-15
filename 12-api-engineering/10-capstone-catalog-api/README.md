# 10 -- Capstone: Hardened Catalog API

## Backstory

Six prototypes later, the marketplace team wants the real thing: one catalog
API that combines everything you've built across this module instead of six
disconnected demos. Product listing has to page through 200,000 rows without
falling over at depth. The category summary box needs a cache that is
actually correct, not just fast. The search endpoint is public, gets
scraped, and has to defend itself both from being hammered and from being
injected into. And a handful of routes need to know who's calling -- with
tokens that actually stop working once they've been used, not just tokens
that expire eventually.

None of the individual pieces are new. What's new is that they all have to
work *at the same time*, inside one service, and the service still has to
be correct when Redis falls over, when a script fires a UNION-based payload
at your search box, when twenty requests hit your rate limiter in the same
millisecond, and when someone tries to replay a refresh token they already
used. A catalog API that works great until any one of those happens is not
the thing being asked for here.

This is a multi-evening build, done in three checkpoints: get the steady
state right (CP1), then make it survive adversarial conditions (CP2), then
write down what you actually built and prove it still holds (CP3).

## What's given

- `src/app.py` -- a FastAPI `app` with every route and helper function
  defined, bodies `raise NotImplementedError`. The module docstring and each
  function's docstring spell out the exact contract: request/response
  shapes, the `X-Cache: HIT/MISS/BYPASS` header contract, the atomic SQL
  shapes for idempotent refresh-token rotation, and which Redis operations
  need to survive Redis being unreachable and which don't. Read
  `src/app.py`'s module docstring before starting -- it explains WHY refresh
  tokens need a database row at all, which is the one piece of this capstone
  that isn't a straight recombination of tasks 01-06.
- The shared, READ-ONLY `shop` schema (Postgres, port 54312; 200,000
  products, 20,000 users, ids contiguous) and a shared Redis (port 6312).
  Both are already running. **Never write to `shop`.**
- The module harness: `harness.common` (`pg_conn`, `redis_port`,
  `verify_password`, `build_password`, `load_ground_truth`, ...),
  `harness.service` (`run_app`, `run_app_subprocess`, `asgi_client`),
  `harness.load` (`bombard`).
- Three checkpoint validators: `tests/validate_cp1.py`, `validate_cp2.py`,
  `validate_cp3.py`.
- `DESIGN.md` -- a design-memo template with six sections to fill in for
  CP3, one per subsystem this capstone builds.

## What's required

Implement `src/app.py`. The work is graded in three checkpoints.

### CP1 -- steady state (`validate_cp1.py`)

**Build:** the base service against a healthy stack -- cursor pagination
over `shop.products` (task 01's technique, plus an optional `category_id`
filter), a Redis cache-aside category summary with a real TTL and an
explicit invalidation route (task 02's technique), an atomic per-key rate
limiter + quota guarding `/catalog/search` (task 03's technique), and JWT
login/refresh/protected-route auth backed by the seeded `shop.users` table
(fixture passwords via `harness.common.build_password`/`verify_password`).

**Checked:** a full paginated sweep of `/catalog/products` (no filters)
returns every product exactly once -- `count == 200000` AND the id checksum
`== 20000100000`, both together, computed against the committed ground
truth; the category summary's cached (`HIT`) reads equal its uncached
(`MISS`) reads, both matching an oracle the validator computes itself
straight from `shop.products`; a concurrent burst against a fresh API key
admits exactly `RATE_LIMIT` requests, never more; and every protected route
(`/account/me`, the cache-invalidate route) rejects an unauthenticated call
with `401`, then accepts the same call with a real token from `/auth/login`.

### CP2 -- chaos / hardening (`validate_cp2.py`)

**Build:** the same service, now hardened against adversarial input and
failure. This is where the module's security block (task 06) and the
"cache is an optimization, not a dependency" lesson land for real.

**Checked:** a SQL-injection battery against `/catalog/search?q=` (a
UNION-based payload targeting `shop.users`, and a benign-looking payload
full of quotes/`--`/`;`) must never leak another table's data and never
return a 500; forged (wrong-secret), expired, malformed, and **rotated**
(a refresh token replayed after it was already exchanged) tokens must all
be rejected with 401; the rate limiter must not over-admit under a heavier
concurrent burst than CP1's, across multiple keys at once; the cache must
return the SAME correct value to every one of a burst of concurrent readers
hitting a freshly-invalidated key (no torn/stale value); a SEPARATE instance
of your app, launched with Redis pointed at a dead port, must still answer
the category-summary endpoint correctly with `X-Cache: BYPASS` -- HTTP 200,
never 500; and the SAME ground-truth-exact pagination sweep as CP1 must
still pass against the hardened service (hardening must not have broken
correctness).

### CP3 -- design memo + green re-run (`validate_cp3.py`)

**Build:** fill in all six sections of `DESIGN.md` -- cursor pagination at
scale, cache correctness under TTL/invalidation/concurrency, rate limiting
and quota atomicity, JWT issuance/verification/rotation, SQL injection
defense, and Redis as an optional dependency.

**Checked:** every required section has real content (no leftover
placeholder text, a minimum length, grounded in this capstone's actual
vocabulary), THEN `validate_cp1.py` and `validate_cp2.py` are re-run as
SUBPROCESSES and both must still pass. A design memo for a service that no
longer converges, or that regressed on any of CP2's hardening, does not
pass this checkpoint either.

## Completion criteria

From this task's directory:

```bash
uv run python tests/validate_cp1.py
uv run python tests/validate_cp2.py
uv run python tests/validate_cp3.py
```

The task is complete when all three print `PASSED` and exit 0. Any
failure -- a stub still raising `NotImplementedError`, an unfilled
`DESIGN.md`, a leaked SQL injection, a rate limiter that over-admits, a
cache that serves a stale value, a 500 when Redis is down, or a rotated
refresh token that still works -- prints a single `NOT PASSED: <reason>`
line and exits 1.

## Estimated evenings

2-4

## Topics to read up on

- Keyset/cursor pagination at scale (task 01) -- now combined with an
  optional filter predicate in the same keyset query
- Cache-aside invalidation and TTL, and what "the cache must never lie"
  means once concurrent readers and a failing Redis both enter the picture
- Atomic check-and-increment rate limiting (Lua `EVAL` / single round trip)
  and multi-tier limits (burst + sustained), under REAL concurrency, not
  just sequential bursts
- JWT structure and verification (signature, `exp`, custom claims like
  `type`), and why a refresh token needs server-side state to support
  rotation/revocation that a stateless access token does not
- Idempotent/atomic `UPDATE ... RETURNING` as the same pattern task 04 used
  for idempotent inserts, applied here to "has this token already been used"
- SQL injection defense from first principles (not fixing someone else's
  bug this time -- writing the parametrized query correctly from the start)
- Graceful degradation: "optional dependency" vs. "hard dependency," and
  designing a code path that is correct with or without a downstream service
- Structuring a FastAPI app with shared auth dependencies (`Depends`) across
  multiple protected routes

## Off-limits

`.authoring/design.md` (at the module root) holds the harness API contract,
the `shop` schema, the corpus RNG draw order, the committed ground-truth
values, and the verification philosophy behind every task in this module --
spoilers. Don't read it before finishing this task.
