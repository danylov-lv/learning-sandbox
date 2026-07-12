"""CP1 validator for the s11 capstone -- STEADY STATE.

Spins up `mock_peer` with the committed corpus (rebuilt in-memory via
`generate.build_corpus(seed, n_pages)` -- pure, no file I/O, so this
validator does not depend on `data/corpus.json` existing on disk; only
`data/ground-truth.json`, which IS committed, needs to be present), a
modest `base_latency`, and a `max_concurrency` cap -- no injected errors,
no jitter. Runs the learner's `scrape` over every path and asserts:

  (a) the returned aggregate matches `load_ground_truth()` exactly for
      `count` and `per_category_count`, and within a small float tolerance
      for `price_sum`.
  (b) `peer.stats.max_observed_concurrency <= max_concurrency` (the hard
      invariant the peer's concurrency gate guarantees IS held -- see
      `.authoring/design.md`) AND `> 1` (real concurrency was used, not a
      disguised serial loop).
  (c) no `asyncio.Task` is left alive that this run is responsible for
      (`leaked_tasks(before) == []`).

No wall-clock timing assertion -- this checkpoint is about correctness and
the concurrency invariant, not throughput.

Note on where the leak snapshot is taken: `before = snapshot_tasks()` is
taken BEFORE entering `async with mock_peer(...)`, and `leaked_tasks(before)`
is checked AFTER that block exits (peer fully torn down via `runner.
cleanup()`), not while the peer is still running. `mock_peer`'s own listen
socket keeps an internal "waiting for the next connection" task alive for as
long as the server is up (on Windows' ProactorEventLoop this task's identity
churns -- a fresh Task each time a connection is accepted), which is
legitimate peer-internal bookkeeping, not something `scrape()` created or is
responsible for cleaning up. Checking the diff only across the peer's full
lifetime (started and fully shut down inside the measured window) is what
isolates "did the LEARNER'S code leak a task" from "does the mock peer's own
accept loop still have a live task at the exact instant we happened to
check."

Run from this task's directory:

    uv run python tests/validate_cp1.py
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

MAX_CONCURRENCY = 24
BASE_LATENCY = 0.008
REQUEST_TIMEOUT = 5.0
PEER_SEED = 4001

PRICE_SUM_TOLERANCE = 0.02


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
    before = snapshot_tasks()
    async with mock_peer(
        base_latency=BASE_LATENCY,
        max_concurrency=MAX_CONCURRENCY,
        seed=PEER_SEED,
        corpus=corpus,
    ) as peer:
        agg = await scrape(
            peer,
            paths,
            max_concurrency=MAX_CONCURRENCY,
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

    agg, stats, leaked = run_async(_run(paths, corpus))

    _assert_aggregate(agg, gt)

    if stats.max_observed_concurrency > MAX_CONCURRENCY:
        not_passed(
            f"peer observed max_observed_concurrency={stats.max_observed_concurrency}, "
            f"exceeding the configured cap {MAX_CONCURRENCY} -- scrape() let more than "
            "max_concurrency requests be simultaneously in flight"
        )
    if stats.max_observed_concurrency <= 1:
        not_passed(
            f"peer observed max_observed_concurrency={stats.max_observed_concurrency} -- "
            "scrape() does not appear to use real concurrency (looks like a serial loop)"
        )

    if leaked:
        not_passed(f"tasks leaked after scrape() returned: {leaked}")

    passed(
        f"count={agg['count']} price_sum={agg['price_sum']} "
        f"max_observed_concurrency={stats.max_observed_concurrency} "
        f"throttled={stats.throttled} no leaked tasks"
    )


if __name__ == "__main__":
    main()
