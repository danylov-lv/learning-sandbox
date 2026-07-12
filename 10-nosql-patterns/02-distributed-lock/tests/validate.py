"""Validator for 10-nosql-patterns task 02 -- distributed-lock.

Checks THREE independent things about the learner's src/lock.py:

  1. Mutual exclusion under concurrency -- many threads spin-acquire the SAME
     lock and race on a shared counter inside the critical section; a truly
     exclusive lock never loses an update, so the final count must match
     n_workers * iters EXACTLY.
  2. Safe release -- the classic wrong-owner bug. A lease whose TTL expired
     must NOT be able to delete a different lease's lock via release().
  3. Fencing monotonicity -- successive acquisitions of the same resource
     must hand out strictly increasing fence numbers.

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
from src.lock import RedisLock  # noqa: E402

NAMESPACE = "s10:t02:"

N_WORKERS = 8
ITERS = 15
MUTEX_LOCK_TTL_MS = 1000
SPIN_BACKOFF_S = 0.005
SPIN_TIMEOUT_S = 5.0

SHORT_TTL_MS = 200
EXPIRY_BUFFER_S = 0.35


def _spin_acquire(lock, ttl_ms, timeout=SPIN_TIMEOUT_S):
    """Retry acquire() with a tiny backoff until a Lease comes back, or raise
    if the lock never frees up within `timeout` -- a broken acquire() that
    always returns None must not hang the validator forever."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        lease = lock.acquire(ttl_ms)
        if lease is not None:
            return lease
        time.sleep(SPIN_BACKOFF_S)
    raise RuntimeError(
        f"could not acquire lock {lock.key!r} within {timeout}s -- "
        "acquire() may never be granting the lock"
    )


@guarded
def main():
    client = redis_client()
    redis_flush_prefix(client, NAMESPACE)

    # --- 1. Mutual exclusion under concurrency ---------------------------
    mutex_lock = RedisLock(client, "res-mutex", namespace=NAMESPACE)
    box = {"n": 0}

    def worker_iteration():
        lease = _spin_acquire(mutex_lock, MUTEX_LOCK_TTL_MS)
        v = box["n"]
        time.sleep(0.001)
        box["n"] = v + 1
        if not mutex_lock.release(lease):
            raise RuntimeError(
                "release() returned False for a lease acquired moments ago "
                "and never expired -- release() is not recognizing its own "
                "valid lease"
            )

    run_concurrently(worker_iteration, N_WORKERS, per_worker=ITERS)

    expected = N_WORKERS * ITERS
    if box["n"] != expected:
        not_passed(
            f"mutual exclusion violated: final counter={box['n']}, "
            f"expected exactly {expected} ({N_WORKERS} workers x {ITERS} "
            "iters) -- a correct lock must never lose a racy "
            "read-sleep-write update"
        )

    # --- 2. Safe release: the wrong-owner bug -----------------------------
    release_lock = RedisLock(client, "res-release", namespace=NAMESPACE)

    lease_a = release_lock.acquire(SHORT_TTL_MS)
    if lease_a is None:
        not_passed("acquire() failed on a fresh, unheld lock key")

    time.sleep(SHORT_TTL_MS / 1000 + EXPIRY_BUFFER_S)

    lease_b = release_lock.acquire(5000)
    if lease_b is None:
        not_passed(
            "acquire() failed to re-acquire a lock whose TTL had already "
            "expired"
        )
    if lease_a.token == lease_b.token:
        not_passed(
            "acquire() returned the same token for two different "
            "acquisitions -- tokens must be freshly unique per call"
        )

    if release_lock.release(lease_a):
        not_passed(
            "release(leaseA) returned True after leaseA's TTL expired and "
            "leaseB was acquired by someone else -- this is the wrong-owner "
            "DEL bug: a naive release deleted a lock it no longer owned"
        )

    held_token = client.get(release_lock.lock_key)
    if held_token != lease_b.token:
        not_passed(
            f"lock key {release_lock.lock_key!r} does not hold leaseB's "
            f"token after release(leaseA): expected {lease_b.token!r}, got "
            f"{held_token!r} -- leaseA's stale release corrupted leaseB's "
            "lock"
        )

    if not release_lock.release(lease_b):
        not_passed("release(leaseB) returned False for its own valid, unexpired lease")

    if client.get(release_lock.lock_key) is not None:
        not_passed(
            f"lock key {release_lock.lock_key!r} still present after "
            "release(leaseB) reported success"
        )

    # --- 3. Fencing monotonicity ------------------------------------------
    fence_lock = RedisLock(client, "res-fence", namespace=NAMESPACE)
    fences = []
    for _ in range(5):
        lease = fence_lock.acquire(1000)
        if lease is None:
            not_passed("acquire() failed on an uncontended lock during the fencing check")
        fences.append(lease.fence)
        if not fence_lock.release(lease):
            not_passed("release() failed for a fresh, unexpired, self-held lease")

    for prev, cur in zip(fences, fences[1:]):
        if cur <= prev:
            not_passed(
                f"fencing tokens not strictly increasing: {fences} -- each "
                "successful acquire of the same resource must yield a "
                "higher fence than the last"
            )

    passed(
        f"mutual exclusion held ({box['n']}/{expected}); wrong-owner release "
        f"correctly rejected; fences strictly increasing: {fences}"
    )


if __name__ == "__main__":
    main()
