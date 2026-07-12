"""Validator for 10-nosql-patterns task 01 -- rate-limiter.

Checks THREE behavioral properties of the learner's src/limiter.py, all
independent of machine speed (no wall-clock throughput thresholds):

  1. No over-admission, and admits up to the limit exactly: with a long
     window (every call lands in the same window) and a limit L, firing
     many concurrent allow() calls against the SAME resource must admit
     EXACTLY L of them. More than L means the check-then-act race let
     extra callers slip through; fewer than L means the implementation
     under-admits.
  2. Per-resource isolation: two different resources have independent
     budgets -- exhausting one must not affect the other.
  3. Window reset semantics: after the window elapses, a resource's budget
     becomes available again.

Run from this task's directory:

    uv run python tests/validate.py
"""

import sys
import time
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))
sys.path.insert(0, str(TASK_ROOT))

from harness.common import (  # noqa: E402
    guarded,
    not_passed,
    passed,
    redis_client,
    redis_flush_prefix,
    run_concurrently,
)
from src.limiter import RateLimiter  # noqa: E402

NAMESPACE = "s10:t01:"

# Check 1: no over-admission under concurrency.
LIMIT = 50
CONCURRENT_CALLS = 500
LONG_WINDOW = 60.0

# Check 2: per-resource isolation.
ISOLATION_LIMIT = 5

# Check 3: window reset.
SHORT_WINDOW = 1.0
RESET_LIMIT = 3


@guarded
def main():
    client = redis_client()
    # The default redis-py connection pool caps at 100 connections; this
    # validator deliberately fires more concurrent callers than that to
    # prove no over-admission, so widen the pool to match.
    client.connection_pool.max_connections = CONCURRENT_CALLS + 50
    redis_flush_prefix(client, NAMESPACE)

    # --- 1. No over-admission + admits up to the limit exactly ---------
    limiter = RateLimiter(client, limit=LIMIT, window_seconds=LONG_WINDOW, namespace=NAMESPACE)

    results = run_concurrently(
        lambda: limiter.allow("shop.example"),
        n_workers=CONCURRENT_CALLS,
    )
    admitted = sum(1 for r in results if r is True)

    if admitted > LIMIT:
        not_passed(
            f"admitted {admitted} calls out of {CONCURRENT_CALLS} concurrent "
            f"allow() calls against a limit of {LIMIT} -- over-admission, "
            "the check-then-act is not atomic"
        )
    if admitted < LIMIT:
        not_passed(
            f"admitted only {admitted} calls out of {CONCURRENT_CALLS} concurrent "
            f"allow() calls against a limit of {LIMIT} -- under-admission, expected "
            f"exactly {LIMIT}"
        )

    non_bool = [r for r in results if not isinstance(r, bool)]
    if non_bool:
        not_passed(f"allow() must return a bool, got a non-bool result: {non_bool[0]!r}")

    # --- 2. Per-resource isolation ---------------------------------------
    redis_flush_prefix(client, NAMESPACE)
    iso_limiter = RateLimiter(client, limit=ISOLATION_LIMIT, window_seconds=LONG_WINDOW, namespace=NAMESPACE)

    a_results = [iso_limiter.allow("resource-a") for _ in range(ISOLATION_LIMIT)]
    if not all(a_results):
        not_passed(
            f"resource-a: expected all of the first {ISOLATION_LIMIT} allow() calls "
            f"to be admitted, got {a_results}"
        )
    a_over = iso_limiter.allow("resource-a")
    if a_over is not False:
        not_passed("resource-a: expected the call beyond the limit to be rejected")

    b_results = [iso_limiter.allow("resource-b") for _ in range(ISOLATION_LIMIT)]
    if not all(b_results):
        not_passed(
            f"resource-b's budget was affected by resource-a's -- expected all "
            f"{ISOLATION_LIMIT} calls to be admitted independently, got {b_results}"
        )

    # --- 3. Window reset semantics ---------------------------------------
    redis_flush_prefix(client, NAMESPACE)
    reset_limiter = RateLimiter(client, limit=RESET_LIMIT, window_seconds=SHORT_WINDOW, namespace=NAMESPACE)

    exhaust = [reset_limiter.allow("reset.example") for _ in range(RESET_LIMIT)]
    if not all(exhaust):
        not_passed(f"expected the first {RESET_LIMIT} calls to be admitted, got {exhaust}")
    over = reset_limiter.allow("reset.example")
    if over is not False:
        not_passed("expected the call beyond the limit to be rejected before the window elapses")

    time.sleep(SHORT_WINDOW + 0.3)

    after_reset = reset_limiter.allow("reset.example")
    if after_reset is not True:
        not_passed(
            "expected allow() to admit again once the window elapsed -- budget did "
            "not reset"
        )

    redis_flush_prefix(client, NAMESPACE)
    passed(
        f"no over-admission ({admitted}/{CONCURRENT_CALLS} concurrent calls admitted, "
        f"limit={LIMIT}); resources isolated; window reset observed"
    )


if __name__ == "__main__":
    main()
