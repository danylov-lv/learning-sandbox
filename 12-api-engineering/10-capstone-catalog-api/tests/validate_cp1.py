"""CP1 validator for the s12 capstone -- STEADY STATE.

Launches the learner's app against the healthy, shared stack and checks the
four pillars this checkpoint is about, never trusting the app's own numbers:

  (a) A full paginated sweep of /catalog/products (no filters) visits every
      row in shop.products exactly once: count == 200000 AND the id
      checksum == 20000100000, both against the committed ground truth --
      either alone can be gamed by a buggy sweep, both together cannot.
  (b) The category-summary cache is byte-correct: a MISS and the HIT that
      follows it both match an oracle this validator computes itself
      straight from shop.products (never the app's own numbers), and the
      cached values equal the uncached values.
  (c) A concurrent burst of well more than RATE_LIMIT requests against a
      fresh /catalog/search API key admits EXACTLY RATE_LIMIT -- the
      atomicity test; a racy check-and-increment fails here.
  (d) Protected routes reject an unauthenticated call with 401, then accept
      the SAME route with a real token obtained via /auth/login.

Run from this task's directory:

    uv run python tests/validate_cp1.py
"""

import sys
import uuid
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))
sys.path.insert(0, str(TASK_ROOT))

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
from harness.service import run_app  # noqa: E402

from src.app import (  # noqa: E402
    CACHE_PREFIX,
    CAPSTONE_SCHEMA,
    RATE_LIMIT,
    REDIS_PREFIX,
    app,
)

TEST_USER_ID = 1
CATEGORY_IDS = [9, 20]
PRICE_TOLERANCE = 0.01
CONCURRENT_BURST = max(5 * RATE_LIMIT, 40)
SWEEP_LIMIT = 5000


def _reset_schema():
    with pg_conn() as conn:
        conn.execute(f"DROP SCHEMA IF EXISTS {CAPSTONE_SCHEMA} CASCADE")
        conn.commit()


def _user_email(user_id):
    with pg_conn() as conn:
        row = conn.execute("SELECT email FROM shop.users WHERE id = %s", (user_id,)).fetchone()
    if not row:
        not_passed(f"seeded user id={user_id} not found in shop.users")
    return row[0]


def _category_oracle(category_id):
    with pg_conn() as conn:
        row = conn.execute(
            "SELECT count(*)::bigint, COALESCE(sum(price),0)::double precision, "
            "avg(price)::double precision FROM shop.products WHERE category_id = %s",
            (category_id,),
        ).fetchone()
    return {
        "category_id": category_id,
        "product_count": int(row[0]),
        "price_sum": float(row[1]),
        "avg_price": row[2],
    }


def _assert_summary(ctx, body, oracle):
    if body.get("category_id") != oracle["category_id"]:
        not_passed(f"{ctx}: category_id={body.get('category_id')!r}, expected {oracle['category_id']}")
    if body.get("product_count") != oracle["product_count"]:
        not_passed(f"{ctx}: product_count={body.get('product_count')}, oracle expects {oracle['product_count']}")
    price_sum = body.get("price_sum")
    if price_sum is None or abs(float(price_sum) - oracle["price_sum"]) > PRICE_TOLERANCE:
        not_passed(f"{ctx}: price_sum={price_sum}, oracle expects ~{oracle['price_sum']}")
    avg_price = body.get("avg_price")
    if avg_price is None or abs(float(avg_price) - oracle["avg_price"]) > PRICE_TOLERANCE:
        not_passed(f"{ctx}: avg_price={avg_price}, oracle expects ~{oracle['avg_price']}")


async def sweep_products(client, category_id=None, limit=SWEEP_LIMIT):
    """Full cursor sweep of /catalog/products, returns (count, id_checksum)."""
    total = 0
    checksum = 0
    cursor = None
    pages = 0
    while True:
        params = {"limit": limit}
        if cursor is not None:
            params["cursor"] = cursor
        if category_id is not None:
            params["category_id"] = category_id
        r = await client.get("/catalog/products", params=params)
        if r.status_code != 200:
            not_passed(f"GET /catalog/products returned {r.status_code}: {r.text[:200]!r}")
        body = r.json()
        items = body.get("items")
        if items is None:
            not_passed(f"GET /catalog/products response missing 'items': {body!r}")
        for it in items:
            total += 1
            checksum += int(it["id"])
        pages += 1
        next_cursor = body.get("next_cursor")
        if next_cursor is None:
            break
        cursor = next_cursor
        if pages > 200:
            not_passed("pagination sweep did not terminate within 200 pages -- next_cursor never became null")
    return total, checksum


async def _check_cache(client, redis, category_id):
    key = f"{CACHE_PREFIX}{category_id}"
    redis.delete(key)
    oracle = _category_oracle(category_id)
    if oracle["product_count"] == 0:
        not_passed(f"test category {category_id} unexpectedly has 0 products -- pick another")

    r1 = await client.get(f"/catalog/categories/{category_id}/summary")
    if r1.status_code != 200:
        not_passed(f"GET .../summary returned {r1.status_code}: {r1.text[:200]!r}")
    if r1.headers.get("X-Cache") != "MISS":
        not_passed(f"category {category_id}: first GET reported X-Cache={r1.headers.get('X-Cache')!r}, expected MISS")
    body1 = r1.json()
    _assert_summary(f"category {category_id} (MISS)", body1, oracle)

    r2 = await client.get(f"/catalog/categories/{category_id}/summary")
    if r2.headers.get("X-Cache") != "HIT":
        not_passed(f"category {category_id}: second GET reported X-Cache={r2.headers.get('X-Cache')!r}, expected HIT")
    body2 = r2.json()
    _assert_summary(f"category {category_id} (HIT)", body2, oracle)

    for k in ("product_count", "price_sum", "avg_price"):
        v1, v2 = body1.get(k), body2.get(k)
        if abs(float(v1) - float(v2)) > PRICE_TOLERANCE:
            not_passed(f"category {category_id}: cached {k}={v2} != uncached {k}={v1} -- HIT must equal MISS")


async def _check_auth_guard(client):
    r = await client.get("/account/me")
    if r.status_code != 401:
        not_passed(f"GET /account/me with no Authorization header returned {r.status_code}, expected 401")
    r2 = await client.post(f"/catalog/categories/{CATEGORY_IDS[0]}/cache/invalidate")
    if r2.status_code != 401:
        not_passed(f"POST cache/invalidate with no Authorization header returned {r2.status_code}, expected 401")

    email = _user_email(TEST_USER_ID)
    password = build_password(TEST_USER_ID)
    r3 = await client.post("/auth/login", json={"email": email, "password": password})
    if r3.status_code != 200:
        not_passed(f"POST /auth/login for seeded user {TEST_USER_ID} returned {r3.status_code}: {r3.text[:200]!r}")
    tokens = r3.json()
    access = tokens.get("access_token")
    if not access:
        not_passed(f"/auth/login response missing 'access_token': {tokens!r}")

    r4 = await client.get("/account/me", headers={"Authorization": f"Bearer {access}"})
    if r4.status_code != 200:
        not_passed(f"GET /account/me with a freshly-issued valid token returned {r4.status_code}, expected 200")
    me = r4.json()
    if int(me.get("user_id", -1)) != TEST_USER_ID:
        not_passed(f"/account/me returned user_id={me.get('user_id')!r}, expected {TEST_USER_ID}")
    if me.get("email") != email:
        not_passed(f"/account/me returned email={me.get('email')!r}, expected {email!r}")

    r5 = await client.post(
        f"/catalog/categories/{CATEGORY_IDS[0]}/cache/invalidate",
        headers={"Authorization": f"Bearer {access}"},
    )
    if r5.status_code != 200:
        not_passed(f"POST cache/invalidate WITH a valid token returned {r5.status_code}, expected 200")


async def _check_rate_limit(service):
    key = f"cp1-{uuid.uuid4().hex[:12]}"
    url = f"{service.base_url}/catalog/search"
    result = await bombard(
        url,
        concurrency=CONCURRENT_BURST,
        requests=CONCURRENT_BURST,
        request_kwargs={"params": {"q": "phone"}, "headers": {"X-API-Key": key}},
    )
    if result.total != CONCURRENT_BURST:
        not_passed(f"rate-limit burst: expected {CONCURRENT_BURST} total requests, got {result.total}")
    if result.ok != RATE_LIMIT:
        not_passed(
            f"rate-limit burst: {CONCURRENT_BURST} concurrent requests against a fresh API key admitted "
            f"{result.ok}, expected EXACTLY RATE_LIMIT={RATE_LIMIT} -- "
            f"{'more than the limit slipped through (check-and-increment is not atomic)' if result.ok > RATE_LIMIT else 'fewer than the limit passed (limiter rejecting valid requests)'}"
        )
    return result.ok


async def _run(redis):
    async with run_app(app) as service:
        async with service.client(timeout=30.0) as client:
            total, checksum = await sweep_products(client)
            await _check_cache(client, redis, CATEGORY_IDS[0])
            await _check_cache(client, redis, CATEGORY_IDS[1])
            await _check_auth_guard(client)
        admitted = await _check_rate_limit(service)
    return total, checksum, admitted


@guarded
def main():
    gt = load_ground_truth()
    redis = redis_client()
    redis_flush_prefix(redis, REDIS_PREFIX)
    _reset_schema()

    try:
        total, checksum, admitted = run_async(_run(redis))
    finally:
        redis_flush_prefix(redis, REDIS_PREFIX)
        _reset_schema()

    if total != gt["row_counts"]["products"]:
        not_passed(f"full pagination sweep returned {total} products, expected {gt['row_counts']['products']}")
    if checksum != gt["products_id_checksum"]:
        not_passed(f"full pagination sweep id checksum={checksum}, expected {gt['products_id_checksum']}")

    passed(
        f"pagination sweep: count={total} checksum={checksum} (matches ground truth); "
        f"cache MISS==HIT for categories {CATEGORY_IDS}; rate limiter admitted exactly "
        f"{admitted}==RATE_LIMIT under a {CONCURRENT_BURST}-request concurrent burst; "
        f"auth guard rejects unauthenticated calls and accepts a real token"
    )


if __name__ == "__main__":
    main()
