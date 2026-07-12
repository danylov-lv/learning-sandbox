# 09 -- Capstone: Bounded Async Scraping Pipeline

## Backstory

Somebody needs a nightly job that reconciles your view of a partner's
catalog: fetch every one of their product pages and produce a summary --
how many products, their total price, a breakdown per category. The partner
is explicit about their limits (a hard concurrency ceiling, enforced with
HTTP 429) and their reliability (slow, and on a bad night, a meaningful
fraction of requests come back HTTP 500 or just take too long). None of
that is exotic on its own -- you built a rate-capped fetcher in task 05, a
bounded producer/consumer pipeline in task 04, cancellation-safe retries in
task 03, structured fan-out in task 02. The capstone is what happens when
all of those have to work AT THE SAME TIME, inside one function, against a
peer that is both slow AND actively hostile: bounded concurrency that never
trips the cap, backpressure so an in-memory buffer can't grow without limit,
and retries that survive real chaos without ever leaking a task or a
connection -- and the whole thing still has to produce the exact right
numbers, because a partial or silently-wrong catalog view is worse than a
slow one.

## What's given

- `src/scraper.py` -- one function, `scrape(peer, paths, *, max_concurrency,
  queue_maxsize=32, max_retries=3, request_timeout=5.0) -> dict`, currently
  `raise NotImplementedError`. The docstring spells out the exact contract:
  what each parameter controls, what the returned aggregate must contain,
  and the five guarantees (concurrency cap, real concurrency, real
  backpressure, convergence under chaos, no leaks) your implementation must
  hold simultaneously.
- `harness/peer.py`'s `mock_peer` -- the in-process aiohttp server standing
  in for the partner site. `Peer.url(path)` builds request URLs;
  `Peer.stats` tracks `max_observed_concurrency`, `throttled`,
  `error_responses`, and `total_requests` across the run.
- `harness/common.py` -- `load_ground_truth`, `run_async`, `snapshot_tasks`/
  `leaked_tasks`, `guarded`, `passed`/`not_passed`.
- `generate.py`'s `build_corpus(seed, n)` -- the same pure, in-memory corpus
  builder the module's `data/ground-truth.json` was computed from; the
  validators use it directly (no dependency on `data/corpus.json` existing
  on disk) so the exact page set graded against is always reproducible from
  the committed ground truth's `seed`/`n_pages`.
- `DESIGN.md` -- a design-memo template with four sections to fill in for
  CP3.
- Three checkpoint validators: `tests/validate_cp1.py`, `validate_cp2.py`,
  `validate_cp3.py`.

## What's required

Implement `scrape` in `src/scraper.py`. The work is graded in three
checkpoints.

### CP1 -- steady state (`validate_cp1.py`)

**Build:** the base pipeline against a merely slow (no errors, no jitter)
peer -- bounded concurrency via something like an `asyncio.Semaphore`, a
bounded `asyncio.Queue` providing real backpressure between a fetch stage
and an aggregate stage, and the aggregate assembled correctly.

**Checked:** the returned aggregate (`count`, `price_sum`,
`per_category_count`) matches the committed ground truth exactly (`count`
and `per_category_count` exact, `price_sum` within a small float
tolerance); `peer.stats.max_observed_concurrency` is `<= max_concurrency`
(the peer's own concurrency gate makes this a hard invariant -- see
`src/scraper.py`'s docstring) AND `> 1` (real concurrency, not a disguised
serial loop); no `asyncio.Task` is left alive after `scrape` returns.

### CP2 -- chaos (`validate_cp2.py`)

**Build:** the same pipeline, now also robust to a peer that returns HTTP
500 on a meaningful fraction of requests and whose latency jitters --
per-request timeout, bounded retry, without ever leaking a task or a
connection along the way.

**Checked:** the SAME aggregate as CP1 (structural correctness, not a race
-- there is no wall-clock/throughput assertion; timing varies by machine),
the same concurrency-cap invariant held throughout, no leaked tasks, and a
sanity floor proving the chaos configuration genuinely exercised retries
(a minimum fraction of injected 500s, and more total requests than paths).

### CP3 -- design memo + green re-run (`validate_cp3.py`)

**Build:** fill in all four sections of `DESIGN.md` -- how the concurrency
cap is held, how backpressure actually works in your implementation, how
cancellation/timeout/retry fit together under CP2's chaos, and what other
failure modes a pipeline shaped like this one would need to guard against.

**Checked:** every required section is present with real content (no
leftover placeholder, a minimum length, and the memo grounded in this
capstone's actual vocabulary -- backpressure, semaphore, cancellation/
timeout, retry, event loop), THEN CP1 and CP2 are re-run as subprocesses
and both must still pass.

## Completion criteria

Once, from the module root:

```bash
uv run python generate.py
```

Then, from this task's directory:

```bash
uv run python tests/validate_cp1.py
uv run python tests/validate_cp2.py
uv run python tests/validate_cp3.py
```

The task is complete when all three print `PASSED` and exit 0. Any
failure -- including a stub still raising `NotImplementedError`, an
unfilled `DESIGN.md`, exceeding the concurrency cap, a wrong aggregate, or
a leaked task -- prints a single `NOT PASSED: <reason>` line and exits 1.

## Estimated evenings

3-4

## Topics to read up on

- `asyncio.Semaphore` for a hard concurrency ceiling, and why "usually
  stays under the cap" isn't the same guarantee as "structurally cannot
  exceed it"
- Bounded `asyncio.Queue` as backpressure between two independently-paced
  pipeline stages (task 04) -- and why fetch-then-aggregate over a plain
  list is not backpressure at all
- `asyncio.TaskGroup` for structured fan-out (task 02) -- a scope that owns
  every task it starts, so failure or cancellation can't leave orphans
- `asyncio.timeout` / `asyncio.wait_for` scoped to a single attempt versus a
  whole retry sequence, and why that placement matters (task 03)
- Retry-with-cap and backoff, and the difference between "give up
  instantly," "retry forever," and a bounded retry that still guarantees
  eventual correctness under a known failure rate
- Why silently dropping a failed unit of work is a worse failure mode than
  raising loudly, for a job whose whole point is producing a trustworthy
  aggregate

## Off-limits

`.authoring/` (at the module root) holds the harness API contract, the
mock-peer's exact request-handling order, and the corpus/ground-truth
generation details for the whole module -- spoilers. Don't read it before
finishing this task.
