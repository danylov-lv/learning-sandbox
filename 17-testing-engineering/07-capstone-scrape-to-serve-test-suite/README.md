# 07 -- Capstone: a test suite for a scrape-to-serve stack

## Backstory

You own a small scrape-to-serve catalog service: a parser that turns raw
scraped records into clean rows, a Postgres repository that stores them,
a Redis cache in front of single-product lookups, and a FastAPI catalog
API that serves it all to clients. It works. It has worked for months.
Now a big refactor is coming -- someone wants to change how pagination
cursors are built, someone else wants to touch the upsert logic, and you
are the one who has to say "go ahead" or "wait, that will break something"
before either change ships.

You cannot say that honestly without a test suite you actually trust. Not
"the tests are green," but "if this refactor introduces the specific kind
of bug that has bitten this stack before -- a flipped watermark
comparison, a cache TTL that never gets set, a pagination cursor that
skips a row, a 404 that quietly turns into a 200 -- my tests would catch
it." This capstone is you building that suite, layer by layer, and then
proving it with the same mutant-killing technique modules 01-05 used one
layer at a time.

## What's given

- `src/impl.py` -- the correct, complete stack: `parse_price` /
  `normalize_record` (pure parser layer), `CatalogRepo` (Postgres
  repository), `ProductCache` (Redis cache), `make_app` (FastAPI catalog
  API), and the JSON Schemas (`PRODUCT_SCHEMA`, `CATALOG_PAGE_SCHEMA`,
  `ERROR_SCHEMA`) the API's responses must satisfy. Read every docstring
  in it before writing a single test -- it is the contract. **Do not edit
  this file.**
- `src/sut.py` -- generated shim. Your tests import `from src.sut import
  ...`, never `from src.impl import ...` -- that indirection is how
  grading swaps in a mutant implementation without changing your test
  files.
- `tests/conftest.py` -- session-scoped `PostgresContainer("postgres:16")`
  and `RedisContainer("redis:7")` fixtures, plus function-scoped `conn`,
  `repo`, `redis_client`, `cache`, `app`, and `client` fixtures built on
  top of them. This is scaffolding to save you container-lifecycle
  boilerplate, not the deliverable -- you should not need to edit it.
- `tests/test_unit.py`, `tests/test_integration.py`, `tests/test_contract.py`
  -- your three deliverables, currently stubs with TODOs and no active
  tests.
- `DESIGN.md` -- an unfilled test-strategy memo template. Filling this in
  is part of the deliverable (see CP3 below).
- `hints/` -- three hints, direction to concrete approach, if you get
  stuck.
- Docker Desktop must be running for CP2 and CP3 -- they start real
  Postgres and Redis containers.

`.authoring/` is off-limits -- it documents the specific bugs your suites
are graded against. Reading it before finishing defeats the exercise.

## What's required

Three test suites, plus a filled-in strategy memo:

1. **`tests/test_unit.py`** -- unit and property tests for `parse_price`
   and `normalize_record`. Pure functions, no containers needed.
2. **`tests/test_integration.py`** -- integration tests for `CatalogRepo`
   and `ProductCache` against real Postgres and Redis, using the `repo` /
   `cache` fixtures.
3. **`tests/test_contract.py`** -- contract tests for the API built by
   `make_app`, driven over real HTTP via the `client` fixture, validating
   response bodies against the JSON Schemas with `jsonschema`.
4. **`DESIGN.md`** -- filled in with your own writing under each required
   `##` heading (see the template for what each section asks).

Each suite is graded by whether it would catch a real regression at its
layer, not by test count or coverage percentage. A test that always
passes regardless of what the implementation does is worth nothing here.

## The three checkpoints

- **CP1** (`tests/validate_cp1.py`) -- runs only `test_unit.py` against
  the correct implementation, then against a bank of pure-logic mutants
  (parser/normalize bugs: separator confusion, sign bugs, a malformed
  input silently returning something instead of raising, wrong
  whitespace/field handling). No containers, runs in seconds.
- **CP2** (`tests/validate_cp2.py`) -- runs `test_integration.py` and
  `test_contract.py` together against a bank of stateful mutants
  (wrong `ON CONFLICT` target, a dropped commit, pagination or watermark
  off-by-ones, a TTL that never gets set, a non-atomic cache path, a
  wrong Redis namespace, a renamed API field, a wrong HTTP status, a
  `next_cursor` edge case). Needs Docker; each mutant run starts fresh
  containers, so a full pass takes a few minutes.
- **CP3** (`tests/validate_cp3.py`) -- first checks that `DESIGN.md` is
  actually filled in (every required section present, with real content,
  no leftover placeholder text), then re-runs CP1 and CP2 as subprocesses
  and requires both to still pass. This is the "prove the whole thing
  still holds together" gate.

## Completion criteria

Run each from the **module root**, with Docker Desktop running for CP2
and CP3:

```bash
uv run python 07-capstone-scrape-to-serve-test-suite/tests/validate_cp1.py
uv run python 07-capstone-scrape-to-serve-test-suite/tests/validate_cp2.py
uv run python 07-capstone-scrape-to-serve-test-suite/tests/validate_cp3.py
```

Each prints `PASSED` (with a `killed N/N mutants` detail line for CP1/CP2)
and exits 0 when its gate is satisfied, or `NOT PASSED: <reason>` and
exits 1 otherwise. The capstone is done when all three print `PASSED`.

## Estimated evenings

3-4

## Topics to read up on

- The testing pyramid: why unit tests should outnumber integration tests,
  which should outnumber end-to-end/contract tests, and what breaks when
  a codebase gets that shape backwards
- Unit vs. integration vs. contract testing: what each layer can and
  cannot prove about a system, and why a passing unit-test mock is not
  evidence a real dependency behaves the same way
- Property-based testing (`hypothesis`) and stateful/metamorphic
  properties, for the pure parser layer
- `testcontainers`: session- vs. function-scoped fixtures, and the
  cost/benefit of one real container per test run vs. per test
- Mutation testing as a coverage-QUALITY gate -- why "100% line coverage"
  and "this suite would catch a real regression" are different claims,
  and mutant-killing is one way to measure the second one
- Designing a test strategy for a multi-layer system: deciding what each
  layer's tests are responsible for, so you are not re-testing the same
  bug three times in three suites (or, worse, zero times in any of them)
