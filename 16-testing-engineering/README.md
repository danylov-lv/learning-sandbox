# 16 — Testing Engineering

## What this module covers

Testing as an engineering discipline, applied to a production scraper/API
stack: property-based testing with Hypothesis (parser invariants and
stateful models), integration testing against real ephemeral service
containers via testcontainers (Postgres, Redis), consumer contract testing
against a module-12-style FastAPI catalog, and mutation testing to answer
the question every test suite dodges — *would these tests actually catch a
regression?*

## The inversion this module is built on

Every other module in this repo has you write an implementation that the
sandbox tests. **This module reverses it.** Each task ships a GIVEN,
CORRECT implementation (`src/impl.py`) — you read it, you do not edit it —
and *you write the test suite* (`tests/test_*.py`). That is the deliverable.

Grading is **mutant-killing**, not output-checking. A task's validator runs
your suite twice:

1. **Green-on-correct** — your suite must fully pass against the correct
   implementation and collect at least a minimum number of tests. An empty
   suite, an `assert False` suite, or a collection error is rejected here.
2. **Kills every mutant** — the sandbox keeps a hidden bank of *mutants*
   (deliberately broken copies of the implementation, each with one planted
   bug) under `.authoring/mutants/`. Your suite must **fail** against every
   one of them. A mutant your suite still passes against has "survived" —
   meaning a real regression of that kind would ship past your tests — and
   the task is not done until you strengthen the suite to catch it.

Your tests import the system under test from `src.sut` (a generated shim),
never from `src.impl` directly — that indirection is how the grader swaps a
mutant in behind your back without your test file knowing. Task 06 is the
one exception: it grades with the real `cosmic-ray` mutation-testing tool
instead of the built-in harness (you run the tool, read its survivors, and
strengthen your suite until the survivor count hits zero).

## Stack

There is **no module-level `docker-compose.yml`**. Tasks 03, 04, and 07 use
`testcontainers`, which starts ephemeral `postgres:16` / `redis:7`
containers on random host ports and tears them down per test run — nothing
to bring up or down by hand, just a running Docker daemon. Tasks 01, 02,
05, and 06 need no containers at all.

Prerequisites:

- **Docker Desktop running** (tasks 03, 04, 07). The two images
  (`postgres:16`, `redis:7`) are the same tags module 12 uses.
- **`uv`** for the toolchain — `hypothesis`, `pytest`, `testcontainers`,
  `psycopg[binary]`, `redis`, `fastapi`, `httpx`, `jsonschema`, and
  `cosmic-ray` (the mutation tool for task 06; `mutmut` was tried and
  dropped — it refuses to run on native Windows).

## Getting started

```bash
cd 16-testing-engineering
uv sync
```

Then, per task, write your tests and run its validator from the module root:

```bash
uv run python 01-property-based-parsing/tests/validate.py
```

A validator prints exactly one line and exits: `PASSED` (with a
`killed N/N mutants` detail line) on success, or
`NOT PASSED: <reason>` — naming the surviving mutants by their opaque id
(`m03`, `m07`, never by their bug) so the failure message is not itself a
spoiler. No raw tracebacks leak to you.

## Tasks

| # | Task | Needs Docker | Mutants to kill |
|---|------|:---:|:---:|
| 01 | property-based-parsing | — | 6 |
| 02 | stateful-and-metamorphic | — | 6 |
| 03 | integration-postgres-testcontainers | yes | 7 |
| 04 | integration-redis-testcontainers | yes | 7 |
| 05 | contract-tests-api | — | 8 |
| 06 | mutation-testing-taste | — | (cosmic-ray, tool-graded) |
| 07 | capstone-scrape-to-serve-test-suite | yes | 7 (CP1) + 9 (CP2) |

- **01** — Hypothesis property tests for a messy price/currency parser:
  round-trip, output-range, and error-typing invariants, plus concrete
  examples for the separator/sign/currency-case cases random search won't
  reliably hit.
- **02** — a `RuleBasedStateMachine` and metamorphic relations against an
  LRU-cache-with-TTL, driven by an injected deterministic clock (no
  `sleep`s).
- **03** — integration tests against a real Postgres for a `PriceRepo`:
  idempotent upsert, watermark incremental load, keyset pagination.
- **04** — integration tests against a real Redis for an atomic
  `RateLimiter` and a `DedupFilter`.
- **05** — consumer contract tests (httpx ASGI client + jsonschema) against
  a module-12-style catalog API.
- **06** — the reflexive one: run `cosmic-ray` on a given module and its
  given weak-but-green suite, read the survivors, and add tests until the
  survivor count reaches zero.
- **07** (capstone, multi-evening) — a layered suite for a one-file
  scrape→serve stack (parser + Postgres repo + Redis cache + FastAPI),
  split into checkpoints: **CP1** unit + property layer (no containers),
  **CP2** integration + contract layer (testcontainers + ASGI/jsonschema),
  **CP3** a `DESIGN.md` testing-strategy memo, after which CP1 and CP2 are
  re-run as subprocesses and must both still be green.

## Verification philosophy

- **Two independent gates, both enforced.** Passing on the correct
  implementation proves your suite isn't vacuous; killing every mutant
  proves it isn't shallow. A suite that only calls each function once and
  checks it doesn't crash passes the first gate and fails the second — by
  design.
- **Mutants encode realistic regressions**, not typos: wrong `ON CONFLICT`
  target, `>` vs `>=` watermark, a non-atomic check-then-set race window, a
  dropped `next_cursor` at the last page, a currency silently hardcoded to
  USD. Each is chosen so a lazy test can't kill it by accident.
- **Every mutant is killable.** Equivalent mutants (a change with no
  observable behavior difference) are excluded during authoring — if a
  mutant survives, it is because your suite has a real gap, not because the
  mutant is a trick.

## `.authoring/` is off-limits until after a task

`.authoring/design.md` documents the harness contract and the mutant
themes, and `.authoring/mutants/` **is the answer key** — reading it before
you finish tells you exactly which bugs to catch. Read it afterward, if at
all, same rule as every other module.
