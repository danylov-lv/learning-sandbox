# 05 -- Contract tests against a catalog API

## Backstory

Another team owns the catalog service your code depends on. You don't own
its code, you don't get a say in its next refactor, and their own test
suite only proves their internals still work -- it says nothing about
whether the response shape your code parses is still what it was
yesterday. A field gets renamed, a status code quietly changes, a
pagination edge case shifts by one -- their tests stay green, your
production code breaks the next time it deserializes a response.

Consumer-driven contract testing is how you defend against that from
outside their codebase: a test suite that pins the exact wire shape you
depend on -- field names, types, status codes, pagination edges, error
envelopes -- and fails the moment any of it drifts, regardless of why it
drifted or whether the owning team's own tests noticed.

## What's given

- `src/impl.py` -- a correct, self-contained FastAPI catalog service
  (`make_app() -> FastAPI`), backed by a small fixed in-memory product
  list (no database, no network, fully deterministic). Its module
  docstring is the prose contract: cursor pagination on `GET /products`,
  `GET /products/{id}` with a 404 + error-envelope path, and a
  `Cache-Control` header on the collection endpoint. **Read it. Do not
  edit it.**
- `src/contract.json` -- the same contract as JSON Schema: `product`,
  `product_list`, and `error` shapes, ready to hand to
  `jsonschema.validate`.
- `src/sut.py` -- generated, do not edit. Import the app factory from
  here: `from src.sut import make_app`. (This indirection is what lets
  grading swap in a mutated implementation without your test file
  changing at all.)
- `tests/test_contract.py` -- an empty scaffold with TODOs. This is
  YOUR file to fill in; nothing in it passes yet.
- `hints/` -- three files, direction to mechanism to a concrete (still
  incomplete) test-file skeleton, if you get stuck.

**`.authoring/` is off-limits.** It holds the mutant bank used to grade
this task -- opening it before you're done is reading the answer key.

## What's required

Write consumer contract tests in `tests/test_contract.py` against
`src.sut.make_app()`, run in-process via `httpx`'s `ASGITransport` or
FastAPI's `TestClient` -- no server process, no container. At minimum,
cover:

- **Schema conformance** -- every product returned by `/products` and by
  `/products/{id}` validates against `contract.json`'s `product` schema;
  the full `/products` body validates against `product_list`; a 404 body
  validates against `error`.
- **Pagination invariants** -- walking `cursor -> next_cursor -> ...`
  from the first page visits every product exactly once and terminates;
  `next_cursor` is `null` on the last page and a non-null string on every
  page before it.
- **The error contract** -- `GET /products/{id}` for an id that doesn't
  exist returns exactly `404` with the `{"error": {"code", "message"}}`
  envelope, not a 200, not a 500, not a bare `{"detail": ...}`.
- **Type stability** -- `id` is a JSON int, `price` is a JSON string, not
  the other way around.

A suite that only checks `status_code == 200` on the happy path will not
catch any of the regressions this task grades against -- every assertion
needs to look at the body shape, an error path, a pagination edge, or a
type, not just "did it not crash."

## Completion criteria

Run from the **module root** (`16-testing-engineering/`, not this task
directory):

```bash
uv run python 05-contract-tests-api/tests/validate.py
```

The validator runs your suite against the given correct implementation
(must fully pass, and collect at least 4 tests), then against a bank of
mutated implementations, each with exactly one contract-breaking bug. It
prints `PASSED` and `killed N/N mutants` once your suite catches every one
of them, or `NOT PASSED: <reason>` naming which mutant(s) survived.

## Estimated evenings

1-2

## Topics to read up on

- Consumer-driven contract testing (what it is, why it differs from the
  provider's own test suite)
- JSON Schema validation with the `jsonschema` package
- FastAPI `TestClient` / `httpx.ASGITransport` for in-process API testing
  (no real server, no sockets)
- Cursor (keyset) pagination contracts: what "last page" vs "mid-stream"
  actually guarantees to a caller
- Error envelope conventions and why a stable, predictable error shape
  matters as much as the happy path
- Schema/type drift as a category of regression that "it still returns
  200" cannot catch

## Off-limits

`.authoring/` (module root) holds this task's mutant bank and design
notes -- do not open it before (or instead of) finishing this task.
