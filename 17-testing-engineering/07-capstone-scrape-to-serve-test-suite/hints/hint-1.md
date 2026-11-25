Work bottom-up, one checkpoint at a time -- do not try to write all three
suites before running anything.

Start with `tests/test_unit.py` and `tests/validate_cp1.py`. This layer is
pure functions (`parse_price`, `normalize_record`), no fixtures, no
Docker, fastest feedback loop in the whole task. Get `validate_cp1.py`
printing `PASSED / killed N/N mutants` before touching the other two
files at all -- it will teach you the mutant-killing workflow (write a
test, run the validator, see which mutants survive, ask yourself what
assertion would have caught THAT specific one) on the cheapest, fastest
layer, before you pay the container-startup cost of CP2.

Then move to `tests/test_integration.py` (CatalogRepo, ProductCache) and
`tests/test_contract.py` (the API), both graded together by
`validate_cp2.py`. These need Docker Desktop running. Write
`test_integration.py` first and get comfortable with the `repo` / `cache`
fixtures before touching the API -- the API's `GET /products/{sku}` route
calls both `repo.get_by_sku` and `cache.get`/`cache.set` internally, so
understanding those two pieces in isolation first will make the contract
tests much easier to reason about.

Only fill in `DESIGN.md` and run `validate_cp3.py` last, once CP1 and CP2
are both genuinely green -- CP3 re-runs both of them as a gate, so there
is nothing to write in the memo yet if you have not actually hit any
survivors to write about.

Think about which layer is responsible for which class of bug BEFORE you
start writing assertions. If you find yourself writing the exact same
assertion in `test_unit.py` and `test_contract.py`, that's a sign you
have not yet decided which layer owns that invariant -- decide, then
delete the redundant one.
