"""Validator for 12-api-engineering task 03 -- rate limiting and quotas.

Checks the learner's src/app.py limiter, structurally (counts of 200 vs 429),
matching the README's completion criteria. No timing/latency assertions here,
so no baseline file: every check is a count or a header/body shape.

  1. Stub / unimplemented -> clean NOT PASSED (a fresh under-limit request
     that does not return 200 is treated as "not implemented yet").
  2. Under-limit: RATE_LIMIT requests from a fresh key all return 200.
  3. Over-limit: the (RATE_LIMIT+1)-th within the window returns 429 with a
     Retry-After header.
  4. Atomicity under concurrency (the real test): fire well more than
     RATE_LIMIT requests CONCURRENTLY against a fresh key; the number of 200s
     must be EXACTLY RATE_LIMIT. A non-atomic GET-then-INCR limiter lets
     extras through and fails here.
  5. Key isolation: a second key keeps its own fresh budget while the first
     is throttled.
  6. Window reset: after waiting out RATE_WINDOW_SEC, a throttled key can make
     requests again.
  7. Quota: crossing QUOTA_LIMIT (staying under the rate cap per window)
     yields a 429 whose body says quota, not rate; plus a structural check
     that a longer-lived quota key exists under the s12:t03: prefix.

Run from this task's directory:

    uv run python tests/validate.py
"""

import asyncio
import sys
import uuid
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))
sys.path.insert(0, str(TASK_ROOT))

from harness.common import guarded, not_passed, passed, redis_client, redis_flush_prefix, run_async  # noqa: E402
from harness.load import bombard  # noqa: E402
from harness.service import run_app  # noqa: E402

from src.app import (  # noqa: E402
    QUOTA_LIMIT,
    QUOTA_WINDOW_SEC,
    RATE_LIMIT,
    RATE_WINDOW_SEC,
    REDIS_PREFIX,
    app,
)

CONCURRENT_BURST = max(5 * RATE_LIMIT, 40)  # "well more than RATE_LIMIT"
RESET_SLACK_SEC = 0.75  # small margin past the window edge


def _fresh_key(tag):
    return f"itest-{tag}-{uuid.uuid4().hex[:12]}"


async def _get(client, key, q="phone"):
    return await client.get("/search", params={"q": q}, headers={"X-API-Key": key})


async def _check_under_limit(client):
    key = _fresh_key("under")
    for i in range(RATE_LIMIT):
        resp = await _get(client, key)
        if resp.status_code != 200:
            if i == 0:
                not_passed(
                    f"first request from a fresh key returned {resp.status_code}, "
                    f"expected 200 -- limiter not implemented yet? "
                    f"(body: {resp.text[:120]!r})"
                )
            not_passed(
                f"under-limit request #{i + 1}/{RATE_LIMIT} returned {resp.status_code}, "
                f"expected 200 (a fresh key must admit RATE_LIMIT={RATE_LIMIT} before throttling)"
            )
    return key


async def _check_over_limit(client):
    key = _fresh_key("over")
    for i in range(RATE_LIMIT):
        resp = await _get(client, key)
        if resp.status_code != 200:
            not_passed(f"over-limit setup: request #{i + 1} returned {resp.status_code}, expected 200")
    resp = await _get(client, key)
    if resp.status_code != 429:
        not_passed(
            f"request #{RATE_LIMIT + 1} for a key returned {resp.status_code}, expected 429 "
            f"(the rate limit must reject once RATE_LIMIT={RATE_LIMIT} is used in the window)"
        )
    if "retry-after" not in {h.lower() for h in resp.headers}:
        not_passed("429 response is missing the Retry-After header")
    retry_after = resp.headers.get("Retry-After") or resp.headers.get("retry-after")
    try:
        ra = int(retry_after)
    except (TypeError, ValueError):
        not_passed(f"Retry-After header is not an integer number of seconds: {retry_after!r}")
    if ra <= 0 or ra > RATE_WINDOW_SEC + 2:
        not_passed(f"Retry-After={ra}s is implausible for a {RATE_WINDOW_SEC}s rate window")


async def _check_isolation(client):
    key_a = _fresh_key("iso-a")
    for _ in range(RATE_LIMIT):
        await _get(client, key_a)
    throttled = await _get(client, key_a)
    if throttled.status_code != 429:
        not_passed(f"isolation: key A should be throttled (429) after RATE_LIMIT requests, got {throttled.status_code}")
    key_b = _fresh_key("iso-b")
    fresh = await _get(client, key_b)
    if fresh.status_code != 200:
        not_passed(
            f"isolation: a different key B returned {fresh.status_code} while key A is throttled -- "
            f"each key must get its OWN budget (leaking one key's counter onto another)"
        )


async def _check_atomicity(service):
    key = _fresh_key("atomic")
    url = f"{service.base_url}/search"
    result = await bombard(
        url,
        concurrency=CONCURRENT_BURST,
        requests=CONCURRENT_BURST,
        request_kwargs={"params": {"q": "phone"}, "headers": {"X-API-Key": key}},
    )
    if result.total != CONCURRENT_BURST:
        not_passed(f"atomicity: expected {CONCURRENT_BURST} total requests, got {result.total}")
    if result.ok != RATE_LIMIT:
        not_passed(
            f"atomicity: fired {CONCURRENT_BURST} concurrent requests at a fresh key and "
            f"{result.ok} returned 200, but EXACTLY RATE_LIMIT={RATE_LIMIT} should be allowed. "
            f"{'More than the limit slipped through -- the check-and-increment is NOT atomic (a GET-then-INCR race).' if result.ok > RATE_LIMIT else 'Fewer than the limit passed -- the atomic counter is rejecting valid requests.'}"
        )
    return result.ok


async def _check_window_reset(client):
    key = _fresh_key("reset")
    for _ in range(RATE_LIMIT):
        await _get(client, key)
    blocked = await _get(client, key)
    if blocked.status_code != 429:
        not_passed(f"window-reset setup: key should be throttled (429), got {blocked.status_code}")
    await asyncio.sleep(RATE_WINDOW_SEC + RESET_SLACK_SEC)
    after = await _get(client, key)
    if after.status_code != 200:
        not_passed(
            f"window reset: after waiting RATE_WINDOW_SEC={RATE_WINDOW_SEC}s the key returned "
            f"{after.status_code}, expected 200 -- the rate window must expire and refresh the budget"
        )


async def _check_quota(client, redis):
    if QUOTA_LIMIT <= RATE_LIMIT:
        not_passed("misconfigured task: QUOTA_LIMIT must exceed RATE_LIMIT for the quota to be the longer-window cap")
    key = _fresh_key("quota")
    allowed = 0
    quota_body = None
    # Consume QUOTA_LIMIT across as many rate windows as needed, then trip quota.
    # Each burst stays within the rate cap; we wait out the rate window between bursts.
    guard = 0
    while allowed < QUOTA_LIMIT + 1 and guard < QUOTA_LIMIT + RATE_LIMIT + 5:
        guard += 1
        resp = await _get(client, key)
        if resp.status_code == 200:
            allowed += 1
            continue
        body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
        error = str(body.get("error", "")).lower()
        if "quota" in error:
            quota_body = body
            break
        # rate-limited: wait out the rate window and continue toward the quota
        await asyncio.sleep(RATE_WINDOW_SEC + RESET_SLACK_SEC)
    if quota_body is None:
        not_passed(
            f"quota: made {allowed} allowed requests without ever hitting a quota-exceeded 429 "
            f"(QUOTA_LIMIT={QUOTA_LIMIT}); the quota cap did not fire or its body did not say 'quota'"
        )
    if allowed != QUOTA_LIMIT:
        not_passed(
            f"quota: {allowed} requests were allowed before the quota tripped, expected exactly "
            f"QUOTA_LIMIT={QUOTA_LIMIT}"
        )
    # Structural: a longer-lived quota key must exist under the prefix (TTL
    # beyond the short rate window distinguishes the quota tier from rate keys).
    ttls = []
    for k in redis.scan_iter(match=f"{REDIS_PREFIX}*", count=500):
        ttl = redis.ttl(k)
        if ttl and ttl > 0:
            ttls.append(ttl)
    if not ttls or max(ttls) <= RATE_WINDOW_SEC:
        not_passed(
            f"quota: no Redis key under {REDIS_PREFIX!r} has a TTL longer than the rate window "
            f"({RATE_WINDOW_SEC}s) -- expected a separate longer-lived quota counter "
            f"(<= QUOTA_WINDOW_SEC={QUOTA_WINDOW_SEC}s)"
        )
    return allowed


async def _run_all():
    async with run_app(app) as service:
        redis = redis_client()
        async with service.client(timeout=10.0) as client:
            await _check_under_limit(client)
            await _check_over_limit(client)
            await _check_isolation(client)
            atomic_ok = await _check_atomicity(service)
            await _check_window_reset(client)
            quota_allowed = await _check_quota(client, redis)
    return atomic_ok, quota_allowed


@guarded
def main():
    client = redis_client()
    redis_flush_prefix(client, REDIS_PREFIX)
    try:
        atomic_ok, quota_allowed = run_async(_run_all())
    finally:
        redis_flush_prefix(client, REDIS_PREFIX)
    passed(
        f"rate limit={RATE_LIMIT}/{RATE_WINDOW_SEC}s, quota={QUOTA_LIMIT}/{QUOTA_WINDOW_SEC}s; "
        f"concurrent burst of {CONCURRENT_BURST} admitted exactly {atomic_ok} (==RATE_LIMIT); "
        f"quota tripped after exactly {quota_allowed} allowed; key isolation + window reset OK"
    )


if __name__ == "__main__":
    main()
