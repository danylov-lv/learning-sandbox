Mechanism per layer -- what kind of test actually has the power to catch
each mutant class the grading bank plants.

**Parser layer (CP1).** `parse_price` and `normalize_record` are pure --
same input always gives the same output, no state, no I/O. That means a
handful of well-chosen example-based tests PLUS a couple of `hypothesis`
`@given(...)` properties will outperform many more shallow examples.
Concrete example tests should nail down: a specific thousands/decimal
combination (`"$1,234.56"` must be `1234.56`, not `1.23456`), a negative
sign (`"-$5.00"` must be negative, `"$5.00"` must not be), each currency
symbol's mapping, and `pytest.raises(ValueError)` for at least one clearly
malformed string (empty string, no digits at all, two decimal points). A
property worth writing: for any amount you construct and format as a
price string yourself, `parse_price` should recover that amount exactly
-- this catches separator-confusion mutants that a small set of hand-picked
examples might miss by accident. For `normalize_record`, test the
whitespace-collapsing behavior on a title with multiple internal spaces,
and test that each of the four required keys' absence raises `KeyError`
specifically (not some other exception, not a silent default).

**Repository + cache layer (CP2, `test_integration.py`).** Every mutant
here is a STATE bug, not a return-value bug in isolation -- test the state
change, not just that a call "worked." For `CatalogRepo`: call
`upsert_products` twice with an overlapping `sku` and assert the row count
is unchanged and the SECOND call's values are what's in the table
(catches a wrong `ON CONFLICT` target or a `DO NOTHING` swap). Open a
SECOND connection to read back a write (catches a dropped `commit()` --
the same connection that wrote can always see its own uncommitted
writes, so testing through it alone proves nothing about durability).
Construct a row at EXACTLY your watermark value and assert
`load_incremental` excludes it (catches `>` vs `>=` flipped either way).
Walk `page()` across multiple pages by feeding the last row's `id` back
in, and assert the union of everything you saw equals every row you
inserted with no duplicates (catches an off-by-one at either page
boundary). For `ProductCache`: after `cache.set(...)`, use the raw
`redis_client` fixture's `.ttl(key)` to assert a POSITIVE TTL is set (not
just that `get` returns the value back) -- catches "TTL never set."
Assert two different `sku`s produce different Redis keys (catches a wrong
namespace that would let one product's cache entry leak into another's
lookup).

**API layer (CP2, `test_contract.py`).** Validate every response body
against its schema with `jsonschema.validate(instance=..., schema=...)`
-- the schemas set `"additionalProperties": false`, so this one call
catches a renamed field, a dropped field, or an unexpected extra field
all at once, and it also catches type drift (`id` returned as a `str`
would fail the schema's `"type": "integer"`). Walk pagination to
exhaustion (follow `next_cursor` until it comes back `null`) and
separately assert directly on one response that a full page's
`next_cursor` is a real `int` while a short/last page's is `null` --
walking alone can hide a "flipped at the boundary" bug if your stopping
condition happens to tolerate it. For the 404 path, assert the exact
status code `404` (not merely "not 200") AND the body's
`error.code == "not_found"` -- a service could return some other 4xx or
a differently-shaped error body and still not be caught by a looser
check. For the cache-read path, seed a row via `repo`, `GET` it once
through `client` to populate the cache, then either inspect
`redis_client` directly to prove the key exists, or change the underlying
DB row and confirm the API still serves the (now stale) cached value on
a second `GET` -- that is the only way to prove the cache path is
actually being exercised rather than every request just hitting Postgres
directly.
