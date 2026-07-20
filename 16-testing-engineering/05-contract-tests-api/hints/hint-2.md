Four mechanisms, one per invariant category the contract actually needs
tested. A test suite that only asserts `status_code == 200` on the happy
path exercises none of these -- it would pass against a service that
silently renamed a field, or one that never terminates pagination.

**Schema conformance.** Load `src/contract.json` once (`json.loads(Path(...).read_text())`)
and keep the three sub-schemas (`product`, `product_list`, `error`) around
as plain dicts. `jsonschema.validate(instance=response.json(), schema=...)`
raises a `ValidationError` (which fails the test) the moment a field is
missing, renamed, or the wrong JSON type -- that one call is doing the
work of a dozen manual `assert "x" in body` lines, and it also catches
things you didn't think to check for individually, like an *extra*
unexpected field (the schemas here set `"additionalProperties": false`
deliberately).

**Pagination invariants.** Don't just fetch page one and stop. Walk the
whole catalog: start with `cursor=None`, request a page, collect the ids
from `items`, follow `next_cursor` into the next request, repeat until
`next_cursor` comes back `null`. Then check two things about what you
collected: no duplicate ids, and the total count matches however many
products actually exist (query `/products` with a large `limit` once to
find that count, or fetch it another honest way -- don't hardcode a magic
number the docstring doesn't give you). Separately, assert directly on a
single response: the LAST page's `next_cursor` is `null`, and any page
that is NOT the last one has a non-null string `next_cursor`. Walking
alone can miss a "null mid-stream" bug if your walk loop's stopping
condition happens to tolerate it -- write both.

**Error contract.** Request a product id you know doesn't exist (pick one
comfortably outside the real range). Assert the status code is exactly
`404` -- not "not 200", the exact code -- and that the body matches the
`error` schema. Also assert the specific shape by key
(`body["error"]["code"] == "not_found"`), not just schema validity alone
-- a service could satisfy some generic error schema with the wrong code
or a completely different envelope structure that still happens to
validate against a loosely-written schema.

**Type stability.** `jsonschema` catches most of this already if your
schema is precise (it is, here), but it's worth an explicit
`isinstance(item["id"], int)` check too, spelled out because Python's
`bool` is a subtype of `int` -- `isinstance(True, int)` is `True` -- so if
you ever check "is it an int" as your ONLY type gate anywhere in a
learning exercise, keep in mind that particular footgun exists, even
though it's not the failure mode this particular service has. `price`
should be `isinstance(item["price"], str)`, specifically NOT
`isinstance(item["price"], (int, float))`.
