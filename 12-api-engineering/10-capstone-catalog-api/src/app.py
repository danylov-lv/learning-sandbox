"""s12.t10 -- CAPSTONE: a hardened catalog API.

Everything the module built, assembled into one service: cursor pagination
over the shared `shop.products` corpus, a Redis-backed cache-aside summary
with a real TTL/invalidation story, an atomic per-key rate limiter + quota,
and JWT auth (login, refresh-token rotation, a protected route) guarding the
mutating bits. The catalog search endpoint is where the module's SQL
injection lesson comes back one more time -- this time you write the
parametrized query from scratch, nobody hands you a vulnerable one to fix.

Endpoints (see README.md for the full checkpoint breakdown):

  Pagination (no auth):
    GET /catalog/products?limit=&cursor=&category_id=

  Cache-aside summary (no auth on the read; auth on the write):
    GET  /catalog/categories/{category_id}/summary
    POST /catalog/categories/{category_id}/cache/invalidate

  Rate-limited + quota-limited search (no auth, but requires X-API-Key):
    GET /catalog/search?q=&limit=

  JWT auth:
    POST /auth/login
    POST /auth/refresh
    GET  /account/me

Postgres: this capstone owns schema t10 (CAPSTONE_SCHEMA below) for the ONE
piece of writable state the whole service needs -- refresh-token rotation
bookkeeping (see "Why refresh tokens need a database row" below). Every read
elsewhere comes from the shared, READ-ONLY `shop` schema. Never write to
`shop`, not a row, not a column.

Redis: every key lives under REDIS_PREFIX = "s12:t10:". The cache and the
rate limiter are two INDEPENDENT uses of the same Redis instance. CP2's
"Redis is unavailable" drill targets ONLY the cache path (see the summary
endpoint's docstring for the exact X-Cache: BYPASS contract) -- the rate-
limited search endpoint's behavior when Redis is down is not graded, so
don't over-build for it.

IMPORTANT pitfall, read before writing any Redis code: `harness.common.
redis_client()` is a VALIDATOR-ONLY helper -- on a connection failure it
calls `sys.exit(1)`. Using it inside a request handler that is supposed to
degrade gracefully would take the whole process down with it, which is
exactly backwards. For any request-path Redis access, build your own
`redis.Redis(host=..., port=redis_port(), decode_responses=True, ...)`
client (a short `socket_connect_timeout`/`socket_timeout` is worth setting)
and catch `redis.exceptions.RedisError` around each actual command, falling
back to Postgres on any failure.

Why refresh tokens need a database row: a JWT's signature and `exp` claim
stay valid until they expire, no matter how many times the token is used --
that's the whole point of a stateless token. But "rotated JWTs must be
rejected" (README) means a refresh token that has ALREADY been exchanged for
a new pair must stop working, even though it's still cryptographically
valid and unexpired. Cryptographic validity alone cannot express "already
used" -- only a stateful check can. That's what `t10.refresh_tokens.revoked`
is for: the JWT's `jti` claim names a row, and rotating flips that row's
`revoked` flag atomically. A refresh implementation that only calls
`jwt.decode(...)` and never touches the database cannot pass this checkpoint
by construction, regardless of how correct the JWT handling otherwise is.
"""

import sys
from contextlib import asynccontextmanager
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parents[2]
if str(MODULE_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE_ROOT))

import jwt  # noqa: E402
from fastapi import Depends, FastAPI, Header, HTTPException, Query  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from harness.common import pg_conn, redis_port, verify_password  # noqa: E402

# --------------------------------------------------------------------------
# Fixed contract constants -- validators import these names directly, so
# your app and the validators always agree on limits/prefixes/TTLs. Do not
# rename or hardcode different numbers in your handlers.
# --------------------------------------------------------------------------

CAPSTONE_SCHEMA = "t10"

# Given as infrastructure, not the exercise: the DDL for this task's own
# schema, applied automatically on startup via `lifespan` below (re-runs
# safely every time the app boots, including right after a validator's own
# `DROP SCHEMA t10 CASCADE`). `jti` defaults server-side via `gen_random_
# uuid()` (built into Postgres 13+, no extension needed) so a fresh row's id
# never has to round-trip back to Python before you can use it -- INSERT
# with `RETURNING jti` hands it back in the same statement.
SCHEMA_SQL = f"""
CREATE SCHEMA IF NOT EXISTS {CAPSTONE_SCHEMA};

CREATE TABLE IF NOT EXISTS {CAPSTONE_SCHEMA}.refresh_tokens (
    jti         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     INTEGER NOT NULL,
    revoked     BOOLEAN NOT NULL DEFAULT false,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at  TIMESTAMPTZ NOT NULL
);
"""

REDIS_PREFIX = "s12:t10:"
CACHE_PREFIX = f"{REDIS_PREFIX}cache:summary:"
CACHE_TTL_SECONDS = 60

RATE_PREFIX = f"{REDIS_PREFIX}rate:"
QUOTA_PREFIX = f"{REDIS_PREFIX}quota:"
RATE_LIMIT = 10
RATE_WINDOW_SEC = 2
QUOTA_LIMIT = 40
QUOTA_WINDOW_SEC = 30

JWT_ALGORITHM = "HS256"
# A fixture secret for this exercise, exactly like the module's fixture
# passwords -- never reuse a hardcoded secret like this for anything real.
JWT_SECRET = "s12-t10-capstone-fixture-secret-do-not-reuse"
ACCESS_TOKEN_TTL_SECONDS = 300
REFRESH_TOKEN_TTL_SECONDS = 3600

PRODUCTS_LIMIT_DEFAULT = 100
PRODUCTS_LIMIT_MAX = 5000
SEARCH_LIMIT_DEFAULT = 20
SEARCH_LIMIT_MAX = 100


# --------------------------------------------------------------------------
# App wiring (given) -- applies SCHEMA_SQL on boot so t10.refresh_tokens
# always exists before the first request lands.
# --------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    with pg_conn() as conn:
        conn.execute(SCHEMA_SQL)
        conn.commit()
    yield


app = FastAPI(title="s12.t10 capstone catalog API", lifespan=lifespan)


@app.exception_handler(NotImplementedError)
async def _not_implemented(request, exc):
    return JSONResponse(
        status_code=501,
        content={"detail": "endpoint not implemented yet -- implement it in src/app.py"},
    )


class LoginRequest(BaseModel):
    email: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class LimitDecision:
    """Result of one rate/quota check -- same shape task 03 used.

    allowed:     True if the request may proceed.
    which:       None when allowed; "rate" or "quota" when rejected.
    retry_after: whole seconds until the offending window frees up.
    """

    def __init__(self, allowed: bool, which: str | None, retry_after: int):
        self.allowed = allowed
        self.which = which
        self.retry_after = retry_after


# --------------------------------------------------------------------------
# You implement everything below this line.
# --------------------------------------------------------------------------

def make_access_token(user_id: int) -> str:
    """Mint a signed access JWT for `user_id`.

    Claims: at least `{"sub": str(user_id), "type": "access", "iat": <now>,
    "exp": <now + ACCESS_TOKEN_TTL_SECONDS>}`. Sign with `JWT_SECRET` /
    `JWT_ALGORITHM` via `jwt.encode(...)`. Purely stateless -- no database
    row for access tokens, unlike refresh tokens (see the module docstring).
    """
    raise NotImplementedError


def make_refresh_token(user_id: int) -> str:
    """Mint a signed refresh JWT for `user_id`, backed by a NEW row in
    `t10.refresh_tokens`.

    Required shape:
      1. INSERT a row into `t10.refresh_tokens` (`user_id`, `expires_at` =
         now + REFRESH_TOKEN_TTL_SECONDS) and get its `jti` back via
         `RETURNING jti` -- this is the ONLY place a refresh-token row is
         created.
      2. Encode a JWT whose claims include at least `{"sub": str(user_id),
         "type": "refresh", "jti": <the row's jti as a string>, "iat":
         <now>, "exp": <now + REFRESH_TOKEN_TTL_SECONDS>}`, signed the same
         way as `make_access_token`.

    The `jti` claim is what lets `/auth/refresh` find and atomically flip
    the matching row later -- the JWT and the database row must agree on
    this value.
    """
    raise NotImplementedError


def decode_token(token: str, expected_type: str) -> dict:
    """Verify and decode `token`, returning its claims dict.

    Must verify BOTH the signature (`JWT_SECRET`/`JWT_ALGORITHM`) and the
    expiry (`jwt.decode` checks `exp` automatically unless told not to) via
    PyJWT, AND that the decoded `type` claim equals `expected_type`
    ("access" or "refresh") -- a refresh token presented where an access
    token is expected (or vice versa) must be rejected here, not silently
    accepted just because the signature happens to be valid.

    Raise on any failure (bad signature, expired, malformed, wrong type) --
    callers convert whatever you raise into HTTP 401. A single exception
    type or PyJWT's own exception hierarchy (`jwt.PyJWTError` and
    subclasses) both work; pick whichever is easiest for callers to catch.
    """
    raise NotImplementedError


def require_user(authorization: str | None = Header(default=None)) -> int:
    """FastAPI dependency for protected routes: `Depends(require_user)`.

    Expects an `Authorization: Bearer <access_token>` header. Missing
    header, missing "Bearer " prefix, or a token that fails
    `decode_token(token, "access")` -> `raise HTTPException(401, ...)`.
    On success, return the user id as an `int` (from the token's `sub`
    claim).

    This is the single choke point every protected endpoint below routes
    through -- get the 401 cases right here once, rather than re-checking
    in every handler.
    """
    raise NotImplementedError


async def check_and_consume(api_key: str) -> LimitDecision:
    """Atomically check + increment BOTH the rate counter and the quota
    counter for `api_key`, exactly like task 03's limiter.

    Requirements (see task 03's README/hints if you need a refresher --
    this is the same problem, same fix):
      - Rate: at most RATE_LIMIT requests per RATE_WINDOW_SEC per key,
        under key `RATE_PREFIX + api_key`.
      - Quota: at most QUOTA_LIMIT requests per QUOTA_WINDOW_SEC per key,
        under key `QUOTA_PREFIX + api_key`.
      - ATOMIC check-and-increment for each counter (one Redis round trip /
        Lua EVAL) -- a GET-then-INCR pair races under concurrency.
      - Check-and-increment the RATE counter first; only if it passes do you
        touch the quota counter. A rate-rejected request must NOT consume
        quota budget.
      - On rejection, `retry_after` is the offending counter's remaining TTL
        in whole seconds.

    Build your own `redis.Redis(host=..., port=redis_port(), decode_
    responses=True)` client here -- this path is not part of CP2's Redis-
    unavailable drill, so it does not need the try/except-and-fall-back
    treatment the cache endpoint below does.
    """
    raise NotImplementedError


@app.post("/auth/login")
async def login(payload: LoginRequest):
    """Authenticate against the seeded `shop.users` table.

    1. `SELECT id, password_hash FROM shop.users WHERE email = %s`.
    2. If no row, OR `verify_password(payload.password, password_hash)` is
       False: `raise HTTPException(401, detail="invalid credentials")` --
       use the SAME message for "no such email" and "wrong password" so the
       endpoint doesn't leak which emails are registered.
    3. On success: `make_access_token(user_id)` + `make_refresh_token(
       user_id)`, respond 200 with
       `{"access_token", "refresh_token", "token_type": "bearer",
       "expires_in": ACCESS_TOKEN_TTL_SECONDS}`.

    Log in as any seeded user with `harness.common.build_password(user_id)`
    for the plaintext -- see the module's fixture-password contract.
    """
    raise NotImplementedError


@app.post("/auth/refresh")
async def refresh(payload: RefreshRequest):
    """Rotate a refresh token: exchange a valid, not-yet-used refresh token
    for a brand-new access/refresh pair, and permanently invalidate the old
    refresh token.

    1. `decode_token(payload.refresh_token, "refresh")` -- any failure
       (forged, expired, malformed, wrong type) -> 401.
    2. Atomically rotate the matching database row in ONE statement:
       `UPDATE t10.refresh_tokens SET revoked = true
        WHERE jti = %s AND revoked = false AND expires_at > now()
        RETURNING user_id`.
       If this returns no row, the token has ALREADY been rotated (reused),
       or its database row expired -- 401 either way. This is what makes
       "rotated JWTs must be rejected" true even though the JWT itself is
       still cryptographically valid: the atomic UPDATE...RETURNING is the
       single point where "has this token been used before" is decided,
       the same shape as task 04's INSERT...ON CONFLICT...RETURNING for
       idempotency -- one round trip, no read-then-write race.
    3. On success, mint a NEW pair for the same user_id (a NEW row, a NEW
       jti) and respond 200 with the same shape `/auth/login` uses.
    """
    raise NotImplementedError


@app.get("/account/me")
async def me(user_id: int = Depends(require_user)):
    """Protected route: return the caller's own identity.

    `SELECT email FROM shop.users WHERE id = %s`. Respond 200 with
    `{"user_id": user_id, "email": email}`. `require_user` has already
    rejected missing/invalid/expired/forged/wrong-type tokens with 401
    before this body runs.
    """
    raise NotImplementedError


@app.get("/catalog/products")
async def list_products(
    limit: int = Query(PRODUCTS_LIMIT_DEFAULT),
    cursor: int | None = Query(default=None),
    category_id: int | None = Query(default=None),
):
    """Keyset (cursor) pagination over `shop.products`, ordered by id ASC,
    same technique as task 01's `/products/cursor` plus an optional filter.

    - Clamp `limit` to `[1, PRODUCTS_LIMIT_MAX]`.
    - `cursor` missing/None/<= 0 means "start from the beginning" (`WHERE
      id > 0` already selects everything, since ids start at 1).
    - `category_id`, if given, adds `AND category_id = %s` to the WHERE
      clause -- still a single indexed keyset scan, no OFFSET anywhere.
    - Query shape: `WHERE id > %s [AND category_id = %s] ORDER BY id
      LIMIT %s`.
    - Response: `{"items": [...], "next_cursor": <id-or-null>}`. Each item
      at least `{"id", "title", "price", "category_id"}`. `next_cursor` is
      the id of the LAST item on a full page, or `null` once a page comes
      back short/empty.

    A full sweep with no `category_id`/`cursor` filter (page after page
    until `next_cursor` is null) must visit every row in `shop.products`
    exactly once -- this is what CP1/CP2/CP3 all check against the
    committed ground truth.
    """
    raise NotImplementedError


@app.get("/catalog/categories/{category_id}/summary")
async def category_summary(category_id: int):
    """Cache-aside category summary -- same contract as task 02's, plus a
    third state CP2 specifically drills: Redis being unreachable.

    Compute (on a cache miss, or when Redis is unavailable) directly from
    Postgres: `{"category_id", "product_count", "price_sum", "avg_price"}`
    for `shop.products WHERE category_id = %s` (count / sum / avg).

    Three `X-Cache` outcomes, all valid, all must return HTTP 200:
      - `HIT`  -- a cache entry existed under `CACHE_PREFIX + str(
                  category_id)`; served straight from Redis, Postgres never
                  touched.
      - `MISS` -- no cache entry existed, but Redis itself is reachable:
                  compute from Postgres, `SET` the result with
                  `CACHE_TTL_SECONDS` TTL, then return it.
      - `BYPASS` -- a Redis operation raised (any `redis.exceptions.
                  RedisError`, e.g. because Redis is pointed at a dead port
                  in CP2's degradation drill): compute from Postgres and
                  return it WITHOUT attempting to write back to Redis (it's
                  presumably still down). This is the "cache is an
                  optimization, not a dependency" case -- the endpoint must
                  still answer 200 with correct data, never a 500, no
                  matter what Redis is doing.

    Wrap every Redis call (GET and SET) for this endpoint in its own
    try/except for `redis.exceptions.RedisError` -- a failure on the GET
    should fall through to computing from Postgres (BYPASS), and a failure
    on the subsequent SET should not turn a perfectly good Postgres-computed
    answer into an error response.
    """
    raise NotImplementedError


@app.post("/catalog/categories/{category_id}/cache/invalidate")
async def invalidate_category_cache(category_id: int, user_id: int = Depends(require_user)):
    """Protected route: drop the cached summary for `category_id` so the
    next GET recomputes it.

    Delete the Redis key `CACHE_PREFIX + str(category_id)`. Respond 200
    whether or not a key was actually there, AND even if Redis itself is
    unreachable (catch `redis.exceptions.RedisError` around the delete and
    still return 200 -- there's nothing meaningful to invalidate if the
    cache is already down, so this is a no-op, not a failure).
    `require_user` has already rejected an unauthenticated caller with 401
    before this body runs.
    """
    raise NotImplementedError


@app.get("/catalog/search")
async def search(q: str = "", limit: int = Query(SEARCH_LIMIT_DEFAULT), x_api_key: str = Header(...)):
    """Rate-limited + quota-limited product search -- and the endpoint
    CP2's SQL-injection battery targets. This is the one you write clean
    from scratch; nobody hands you a vulnerable version to fix this time.

    1. `check_and_consume(x_api_key)`. On rejection: `429` with a
       `Retry-After` header (whole seconds) and a JSON body whose `error`
       field is `"rate_limited"` or `"quota_exceeded"`.
    2. On success: clamp `limit` to `[1, SEARCH_LIMIT_MAX]`, then run a
       PARAMETRIZED `ILIKE` match against `shop.products.title` -- `q` is
       always a bound parameter, NEVER interpolated into the SQL text (see
       task 06 if you need the reminder of exactly what goes wrong when it
       is, and where the `%` wildcards belong once `q` is a parameter).
       Query shape: `WHERE title ILIKE %s ORDER BY id LIMIT %s`, param
       `f"%{q}%"`.
    3. Respond 200 with `{"items": [...], "count": len(items)}`. Each item
       at least `{"id", "title", "price"}`.

    A payload containing `'`, `--`, `;`, or a `UNION SELECT` against
    `shop.users` must be treated as an ordinary (almost certainly
    non-matching) literal string -- HTTP 200, zero leaked rows from any
    table other than `shop.products`, never a 500.
    """
    raise NotImplementedError
