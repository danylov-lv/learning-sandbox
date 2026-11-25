"""CP2 validator for the s11 capstone -- CHAOS.

Same corpus as CP1, rebuilt in-memory via `generate.build_corpus`, but the
peer is configured with `error_rate` (a fraction of accepted requests come
back HTTP 500) and `jitter` (latency varies request to request) on top of
the same `max_concurrency` cap. The learner's `scrape` must retry through
the injected failures and STILL converge to the EXACT same aggregate as a
healthy run -- structural correctness, not a race against the clock. This
checkpoint deliberately makes NO wall-clock/throughput assertion (timing
varies by machine); it only checks the final result, the concurrency
invariant, and that nothing leaked.

`max_retries` is set generously here (well beyond `scrape`'s own default)
so that, at this `error_rate`, the probability of any single path
exhausting every attempt is astronomically small (see `_expected_failure_
count` below) -- a correct, retrying implementation converges to the exact
ground truth for all practical purposes every run; this is not a flaky
threshold.

Run from this task's directory:

    uv run python tests/validate_cp2.py
"""

import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))
sys.path.insert(0, str(TASK_ROOT))

from generate import build_corpus  # noqa: E402
from harness.common import (  # noqa: E402
    guarded,
    leaked_tasks,
    load_ground_truth,
    not_passed,
    passed,
    run_async,
    snapshot_tasks,
)
from harness.peer import mock_peer  # noqa: E402
from src.scraper import scrape  # noqa: E402

MAX_CONCURRENCY = 20
BASE_LATENCY = 0.006
JITTER = 0.006
ERROR_RATE = 0.2
REQUEST_TIMEOUT = 5.0
MAX_RETRIES = 8  # 9 attempts/path -- see _expected_failure_count
PEER_SEED = 4002

PRICE_SUM_TOLERANCE = 0.02

# Sanity floor: proves the chaos configuration actually exercised retries,
# rather than passing by coincidence with an effectively-healthy peer.
MIN_ERROR_FRACTION = 0.08


def _expected_failure_count(n_pages, error_rate, max_retries):
    """Expected number of paths that exhaust every attempt (1 + max_retries),
    assuming each attempt independently fails with probability `error_rate`.
    Used only to document why MAX_RETRIES is set high enough that this
    checkpoint is a structural test, not a probabilistic gamble."""
    p_all_fail = error_rate ** (max_retries + 1)
    return n_pages * p_all_fail


def _assert_aggregate(agg, expected):
    if not isinstance(agg, dict):
        not_passed(f"scrape() must return a dict, got {type(agg).__name__}")

    if agg.get("count") != expected["count"]:
        not_passed(f"aggregate['count']={agg.get('count')}, expected {expected['count']} exactly")

    price_sum = agg.get("price_sum")
    if not isinstance(price_sum, (int, float)):
        not_passed(f"aggregate['price_sum']={price_sum!r}, expected a number")
    if abs(float(price_sum) - expected["price_sum"]) > PRICE_SUM_TOLERANCE:
        not_passed(
            f"aggregate['price_sum']={price_sum}, expected {expected['price_sum']} "
            f"within {PRICE_SUM_TOLERANCE}"
        )

    got_cat = agg.get("per_category_count") or {}
    exp_cat = expected["per_category_count"]
    missing = [c for c in exp_cat if c not in got_cat]
    if missing:
        not_passed(f"per_category_count missing categories: {missing}")
    extra = [c for c in got_cat if c not in exp_cat]
    if extra:
        not_passed(f"per_category_count has unexpected categories: {extra}")
    for cat, exp_count in exp_cat.items():
        if got_cat[cat] != exp_count:
            not_passed(f"per_category_count[{cat!r}]={got_cat[cat]}, expected {exp_count} exactly")


async def _run(paths, corpus):
    # before/leaked_tasks span the peer's FULL lifetime (created and fully
    # torn down inside this window) rather than being taken while the peer
    # is still running -- see validate_cp1.py's module docstring for why:
    # the peer's own accept-loop task churns identity on Windows and is not
    # something scrape() created or owns.
    before = snapshot_tasks()
    async with mock_peer(
        base_latency=BASE_LATENCY,
        jitter=JITTER,
        max_concurrency=MAX_CONCURRENCY,
        error_rate=ERROR_RATE,
        seed=PEER_SEED,
        corpus=corpus,
    ) as peer:
        agg = await scrape(
            peer,
            paths,
            max_concurrency=MAX_CONCURRENCY,
            max_retries=MAX_RETRIES,
            request_timeout=REQUEST_TIMEOUT,
        )
        stats = peer.stats
    leaked = leaked_tasks(before)
    return agg, stats, leaked


@guarded
def main():
    gt = load_ground_truth()
    n_pages = gt["n_pages"]
    paths = [f"/p/{i}" for i in range(1, n_pages + 1)]
    corpus = build_corpus(gt["seed"], n_pages)

    expected_failures = _expected_failure_count(n_pages, ERROR_RATE, MAX_RETRIES)
    if expected_failures > 1.0:
        not_passed(
            f"CP2 misconfigured: expected ~{expected_failures:.2f} paths to exhaust "
            f"all {MAX_RETRIES + 1} attempts at error_rate={ERROR_RATE} -- raise "
            "MAX_RETRIES or lower ERROR_RATE so convergence is a structural "
            "guarantee, not a coin flip"
        )

    agg, stats, leaked = run_async(_run(paths, corpus))

    if stats.error_responses < n_pages * MIN_ERROR_FRACTION:
        not_passed(
            f"peer only injected {stats.error_responses} HTTP 500s over "
            f"{stats.total_requests} total requests -- expected at least "
            f"{n_pages * MIN_ERROR_FRACTION:.0f}, chaos configuration too weak to "
            "prove retry behavior actually ran"
        )
    if stats.total_requests <= n_pages:
        not_passed(
            f"peer saw only {stats.total_requests} total requests for {n_pages} paths "
            "-- expected more than one request per path on average, meaning scrape() "
            "does not appear to have retried the injected failures at all"
        )

    _assert_aggregate(agg, gt)

    if stats.max_observed_concurrency > MAX_CONCURRENCY:
        not_passed(
            f"peer observed max_observed_concurrency={stats.max_observed_concurrency}, "
            f"exceeding the configured cap {MAX_CONCURRENCY} -- scrape() let more than "
            "max_concurrency requests be simultaneously in flight, even under chaos"
        )
    if stats.max_observed_concurrency <= 1:
        not_passed(
            f"peer observed max_observed_concurrency={stats.max_observed_concurrency} -- "
            "scrape() does not appear to use real concurrency under chaos"
        )

    if leaked:
        not_passed(f"tasks leaked after scrape() returned despite injected failures: {leaked}")

    passed(
        f"converged despite chaos: count={agg['count']} price_sum={agg['price_sum']} "
        f"(error_responses={stats.error_responses}, total_requests={stats.total_requests}, "
        f"max_observed_concurrency={stats.max_observed_concurrency}); no leaked tasks"
    )


if __name__ == "__main__":
    main()
