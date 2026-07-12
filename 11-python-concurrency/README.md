# 11 — Python concurrency

## What this module covers

You already write async code in production (Scrapy pipelines, aiohttp
clients) — you know the shape of `async def` / `await`. What this module
trains is the layer underneath that: how the event loop actually schedules
coroutines, what happens when one of them blocks it, what "structured" means
in structured concurrency, why cancellation without care leaks tasks and
connections, how backpressure keeps a bounded pipeline from falling over, and
when the GIL means you should reach for threads or processes instead of more
`asyncio.gather`. The capstone puts all of it under one bounded async
scraping pipeline.

There are **no docker services** in this module — it is pure Python. In place
of "a slow website to scrape," `harness/peer.py` starts a real aiohttp server
in-process on an ephemeral localhost port and lets you dial in latency,
concurrency caps, rate limits, and injected errors.

## Tasks

- **01** — event-loop-and-blocking: detect and fix a blocking call starving
  the event loop.
- **02** — taskgroup-structured-concurrency: `asyncio.TaskGroup`, sibling
  cancellation on first failure.
- **03** — cancellation-and-timeouts: cancel and time out without leaking
  tasks or connections.
- **04** — backpressure-bounded-queue: a bounded `asyncio.Queue` producer/
  consumer pipeline that doesn't blow past a memory budget.
- **05** — semaphore-rate-limiting: bounded concurrency and a rate cap
  against the mock peer.
- **06** — gil-decision-matrix: asyncio vs. threads vs. multiprocessing,
  benchmarked, not guessed.
- **07** — sync-async-bridging: `run_in_executor` / `asyncio.to_thread`.
- **08** — profiling-py-spy: profile a *live* async process with py-spy.
- **09** — capstone-async-scraper: a bounded async scraping pipeline against
  the mock peer, graded at three checkpoints — CP1 steady state, CP2 chaos
  (errors/timeouts injected), CP3 a short design memo.

## Running

```bash
cd 11-python-concurrency
uv sync
uv run python generate.py       # builds the capstone corpus + ground truth
uv run python NN-task-name/tests/validate.py
```

`generate.py` is deterministic (fixed seed, respects `SCALE`, default `1.0`)
and writes `data/corpus.json` (gitignored) plus the committed
`data/ground-truth.json` the capstone grades against.

Every task imports shared plumbing from `harness/common.py` (pass/fail
helpers, ground-truth loading, `run_async`, leaked-task detection, peak-
memory measurement) and, where it scrapes against a peer, `harness/peer.py`
(the in-process mock server). Validators print `PASSED` or
`NOT PASSED: <reason>` and never leak a raw traceback.

## Profiling (task 08)

py-spy attaches to a **running process** — there is nothing to mock. The task
has you launch a real async app and profile it externally
(`py-spy record` / `py-spy dump`) while it runs, rather than profiling
in-process. On Windows this may require an elevated shell; the task's README
covers the specifics.

## Timing-sensitive tasks use a machine-local baseline

Task 06 (GIL decision matrix) and task 08 (profiling) are the two places this
module makes claims about speed. Neither compares against an absolute number
— every check is relative to a `baseline.py` you run first on your own
machine, which writes a gitignored `*-local.json` that later checks compare
against. This keeps the tasks meaningful on hardware ranging from a laptop to
a CI runner.

## `.authoring/` is off-limits until after a task

`.authoring/` holds spoilers: the harness API contract, the mock-peer knobs
and stats semantics, the corpus schema and RNG draw order, and the committed
ground-truth values. Read it *after* finishing a task, never before.
