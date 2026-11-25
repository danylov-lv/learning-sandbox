"""CP2 validator for the s12 capstone -- CHAOS / HARDENING.

Same service as CP1, now checked under adversarial input and failure:

  (a) SQL-injection battery against /catalog/search?q= -- a UNION-based
      payload targeting shop.users, and a benign-looking payload full of
      quotes/--/;. Both must return HTTP 200 (never 500) and leak nothing.
  (b) JWT trap tests: forged (wrong secret), expired, and malformed access
      tokens are all rejected with 401. A refresh token that has already
      been exchanged (rotated) is rejected on a SECOND use -- proven by
      first showing the FIRST use succeeds (200, a genuinely new token
      pair), so the second use's 401 is not just "everything 401s".
  (c) Rate limiter atomicity under a heavier, two-key SIMULTANEOUS burst
      (stronger than CP1's single-key check) -- exactly RATE_LIMIT admitted
      per key, never more.
  (d) Cache correctness under concurrency: a burst of concurrent readers
      against a freshly-invalidated key must ALL receive the exact oracle
      value -- no torn/stale response.
  (e) Redis-unavailable graceful degradation: a SEPARATE app instance,
      launched as a real subprocess with Redis pointed at a dead port
      (never by stopping the shared Redis container -- other validators may
      be running concurrently), must still answer the category-summary
      endpoint correctly with X-Cache: BYPASS, HTTP 200, never 500.
  (f) Convergence: the SAME ground-truth-exact pagination sweep CP1 checks
      must still pass against the hardened service.

Run from this task's directory:

    uv run python tests/validate_cp2.py
"""

import asyncio
import sys
import time
import uuid
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))
sys.path.insert(0, str(TASK_ROOT))

import jwt  # noqa: E402

from harness.common import (  # noqa: E402
    build_password,
    guarded,
    load_ground_truth,
    not_passed,
    passed,
    pg_conn,
    redis_client,
    redis_flush_prefix,
    run_async,
)
from harness.load import bombard  # noqa: E402
from harness.service import run_app, run_app_subprocess  # noqa: E402

from src.app import (  # noqa: E402
    CACHE_PREFIX,
    CAPSTONE_SCHEMA,
    JWT_ALGORITHM,
    JWT_SECRET,
    RATE_LIMIT,
    REDIS_PREFIX,
    app,
)

from tests.validate_cp1 import (  # noqa: E402
    CATEGORY_IDS,
    PRICE_TOLERANCE,
    TEST_USER_ID,
    _assert_summary,
    _category_oracle,
    _reset_schema,
    _user_email,
    sweep_products,
)

CONCURRENT_BURST_CP2 = max(10 * RATE_LIMIT, 80)
CACHE_CONCURRENCY_N = 25
DEGRADE_CATEGORY_ID = 55
UNION_PAYLOAD = "zzz_nomatch' UNION SELECT id, email, 1.0 FROM shop.users -- "
BENIGN_PAYLOAD = "O'Brien\"s gadget -- ; SELECT 1"


def _dead_port():
    """Bind-then-close an ephemeral port -- nothing listens on it, so a
    connection attempt fails (refused) quickly instead of hanging. Same
    trick harness/service.py's run_app_subprocess uses for its own
    port-finding, applied here to guarantee a closed port on purpose."""
    import socket

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


async def _check_sql_injection(client):
    before = None
    with pg_conn() as conn:
        before = conn.execute("SELECT count(*) FROM shop.products").fetchone()[0]

    for label, payload in (("union", UNION_PAYLOAD), ("benign-metacharacters", BENIGN_PAYLOAD)):
        r = await client.get("/catalog/search", params={"q": payload}, headers={"X-API-Key": f"sqli-{uuid.uuid4().hex[:8]}"})
        if r.status_code != 200:
            not_passed(
                f"SQLi battery ({label}): GET /catalog/search?q={payload!r} returned HTTP "
                f"{r.status_code}, expected 200 (a parametrized query treats this as a literal "
                f"string, never a syntax/server error) -- body: {r.text[:200]!r}"
            )
        body = r.json()
        items = body.get("items")
        if not isinstance(items, list):
            not_passed(f"SQLi battery ({label}): response missing a list 'items': {body!r}")
        if items:
            not_passed(
                f"SQLi battery ({label}): payload {payload!r} unexpectedly matched {len(items)} "
                f"row(s) ({items[:2]!r}) -- no shop.products title contains this payload as a "
                f"literal substring, so a nonempty result means the payload reached raw SQL"
            )

    with pg_conn() as conn:
        after = conn.execute("SELECT count(*) FROM shop.products").fetchone()[0]
    if after != before:
        not_passed(f"shop.products row count changed ({before} -> {after}) after the SQLi battery -- must never mutate the shared schema")


def _mint_forged_token():
    return jwt.encode(
        {"sub": str(TEST_USER_ID), "type": "access", "iat": time.time(), "exp": time.time() + 300},
        "definitely-the-wrong-secret",
        algorithm=JWT_ALGORITHM,
    )


def _mint_expired_token():
    return jwt.encode(
        {"sub": str(TEST_USER_ID), "type": "access", "iat": time.time() - 1000, "exp": time.time() - 10},
        JWT_SECRET,
        algorithm=JWT_ALGORITHM,
    )


async def _check_jwt_traps(client):
    cases = [
        ("forged (wrong secret)", _mint_forged_token()),
        ("expired", _mint_expired_token()),
        ("malformed", "this-is-not-a-jwt-at-all"),
    ]
    for label, token in cases:
        r = await client.get("/account/me", headers={"Authorization": f"Bearer {token}"})
        if r.status_code != 401:
            not_passed(f"JWT trap ({label}): GET /account/me returned {r.status_code}, expected 401")


async def _check_refresh_rotation(client):
    email = _user_email(TEST_USER_ID)
    password = build_password(TEST_USER_ID)
    r_login = await client.post("/auth/login", json={"email": email, "password": password})
    if r_login.status_code != 200:
        not_passed(f"POST /auth/login returned {r_login.status_code}: {r_login.text[:200]!r}")
    original_refresh = r_login.json().get("refresh_token")
    if not original_refresh:
        not_passed(f"/auth/login response missing 'refresh_token': {r_login.json()!r}")

    r1 = await client.post("/auth/refresh", json={"refresh_token": original_refresh})
    if r1.status_code != 200:
        not_passed(f"first use of a fresh refresh token returned {r1.status_code}, expected 200: {r1.text[:200]!r}")
    body1 = r1.json()
    new_refresh = body1.get("refresh_token")
    if not new_refresh:
        not_passed(f"/auth/refresh response missing 'refresh_token': {body1!r}")
    if new_refresh == original_refresh:
        not_passed("/auth/refresh returned the SAME refresh_token it was given -- rotation must issue a NEW token")
    if not body1.get("access_token"):
        not_passed(f"/auth/refresh response missing 'access_token': {body1!r}")

    r2 = await client.post("/auth/refresh", json={"refresh_token": original_refresh})
    if r2.status_code != 401:
        not_passed(
            f"REPLAYING the original (already-rotated) refresh token returned {r2.status_code}, "
            f"expected 401 -- a refresh token must stop working the instant it's exchanged, even "
            f"though its signature and exp are still valid"
        )

    r3 = await client.post("/auth/refresh", json={"refresh_token": new_refresh})
    if r3.status_code != 200:
        not_passed(f"using the NEW refresh token from rotation returned {r3.status_code}, expected 200 -- rotation must not have broken the new token")


async def _check_rate_limit_concurrent(service):
    key_a = f"cp2-a-{uuid.uuid4().hex[:8]}"
    key_b = f"cp2-b-{uuid.uuid4().hex[:8]}"
    url = f"{service.base_url}/catalog/search"

    async def _burst(key):
        return await bombard(
            url,
            concurrency=CONCURRENT_BURST_CP2,
            requests=CONCURRENT_BURST_CP2,
            request_kwargs={"params": {"q": "phone"}, "headers": {"X-API-Key": key}},
        )

    result_a, result_b = await asyncio.gather(_burst(key_a), _burst(key_b))
    for label, result in (("A", result_a), ("B", result_b)):
        if result.ok != RATE_LIMIT:
            not_passed(
                f"heavier concurrent burst ({CONCURRENT_BURST_CP2} simultaneous requests, two keys "
                f"fired at once) for key {label}: admitted {result.ok}, expected EXACTLY "
                f"RATE_LIMIT={RATE_LIMIT}"
            )
    return result_a.ok, result_b.ok


async def _check_cache_concurrency(client, redis, category_id):
    key = f"{CACHE_PREFIX}{category_id}"
    redis.delete(key)
    oracle = _category_oracle(category_id)
    if oracle["product_count"] == 0:
        not_passed(f"test category {category_id} unexpectedly has 0 products -- pick another")

    async def _get():
        return await client.get(f"/catalog/categories/{category_id}/summary")

    responses = await asyncio.gather(*[_get() for _ in range(CACHE_CONCURRENCY_N)])
    for i, r in enumerate(responses):
        if r.status_code != 200:
            not_passed(f"concurrent cache read #{i}: status {r.status_code}, expected 200")
        body = r.json()
        _assert_summary(f"concurrent cache read #{i} (category {category_id})", body, oracle)


async def _run_healthy_checks(redis):
    async with run_app(app) as service:
        async with service.client(timeout=30.0) as client:
            await _check_sql_injection(client)
            await _check_jwt_traps(client)
            await _check_refresh_rotation(client)
            await _check_cache_concurrency(client, redis, CATEGORY_IDS[0])
            total, checksum = await sweep_products(client)
        rate_a, rate_b = await _check_rate_limit_concurrent(service)
    return total, checksum, rate_a, rate_b


async def _check_redis_down():
    dead_port = _dead_port()
    oracle = _category_oracle(DEGRADE_CATEGORY_ID)
    if oracle["product_count"] == 0:
        not_passed(f"degrade-drill category {DEGRADE_CATEGORY_ID} unexpectedly has 0 products -- pick another")

    async with run_app_subprocess(
        "src.app:app",
        env={"PYTHONPATH": str(TASK_ROOT), "SANDBOX_12_REDIS_PORT": str(dead_port)},
    ) as service:
        import httpx

        async with httpx.AsyncClient(base_url=service.base_url, timeout=30.0) as client:
            r = await client.get(f"/catalog/categories/{DEGRADE_CATEGORY_ID}/summary")
            if r.status_code != 200:
                not_passed(
                    f"summary endpoint with Redis pointed at a dead port returned {r.status_code}, "
                    f"expected 200 -- the cache must be an optimization, not a hard dependency"
                )
            x_cache = r.headers.get("X-Cache")
            if x_cache != "BYPASS":
                not_passed(
                    f"summary endpoint with Redis pointed at a dead port reported X-Cache={x_cache!r}, "
                    f"expected BYPASS -- either the degradation path never fired (this drill would be "
                    f"vacuous), or a working Redis call is being wrongly reported as MISS/HIT"
                )
            body = r.json()
            _assert_summary("Redis-down degrade check", body, oracle)

            r2 = await client.get("/catalog/products", params={"limit": 50})
            if r2.status_code != 200:
                not_passed(
                    f"pagination endpoint with Redis pointed at a dead port returned {r2.status_code}, "
                    f"expected 200 -- pagination does not depend on Redis at all and must be unaffected"
                )


@guarded
def main():
    gt = load_ground_truth()
    redis = redis_client()
    redis_flush_prefix(redis, REDIS_PREFIX)
    _reset_schema()

    try:
        total, checksum, rate_a, rate_b = run_async(_run_healthy_checks(redis))
        run_async(_check_redis_down())
    finally:
        redis_flush_prefix(redis, REDIS_PREFIX)
        _reset_schema()

    if total != gt["row_counts"]["products"]:
        not_passed(f"convergence sweep returned {total} products, expected {gt['row_counts']['products']} -- hardening broke correctness")
    if checksum != gt["products_id_checksum"]:
        not_passed(f"convergence sweep id checksum={checksum}, expected {gt['products_id_checksum']} -- hardening broke correctness")

    passed(
        f"SQLi battery blocked (0 leaked rows, no 500s); forged/expired/malformed tokens rejected; "
        f"rotated refresh token rejected on reuse (first use 200, replay 401); rate limiter admitted "
        f"exactly {rate_a}/{rate_b}==RATE_LIMIT under a two-key {CONCURRENT_BURST_CP2}x concurrent "
        f"burst; {CACHE_CONCURRENCY_N} concurrent cache reads all matched the oracle; Redis-down "
        f"degrade check returned X-Cache: BYPASS with correct data; convergence sweep count={total} "
        f"checksum={checksum} still matches ground truth"
    )


if __name__ == "__main__":
    main()
