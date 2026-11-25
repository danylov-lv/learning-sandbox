Start by reading, not writing. `src/impl.py`'s module docstring is the
prose contract; `src/contract.json` is the same contract as JSON Schema.
Read both before opening a test file -- you are the consumer team here,
and a consumer team's first job is understanding exactly what they're
allowed to depend on.

Think about *why* this task exists: some other team owns this service.
Next sprint they refactor it -- rename a field, change a status code,
tweak the pagination edge case -- with every one of their own unit tests
still green, because their tests check their own internals, not your
contract. The only thing standing between that refactor and your service
breaking in production is a test suite that pins down the contract from
the OUTSIDE, the same way your code actually consumes this API. That's
what you're writing.

Get the app running in-process first, before writing any assertions. The
simplest synchronous option is `fastapi.testclient.TestClient(app)` -- it
lets you call `.get("/products")` and get back a real response object with
`.status_code`, `.json()`, `.headers`, no server process, no container, no
network. (If you prefer raw `httpx`, note that `httpx.ASGITransport` is
ASYNC-only on current httpx -- it works with `httpx.AsyncClient`, not the
synchronous `httpx.Client`; a sync `httpx.Client(transport=ASGITransport(...))`
raises `AttributeError: ... has no attribute 'handle_request'`. For a
straightforward sync test suite, reach for `TestClient`.)

Once you can print a raw response body for `/products` and for
`/products/{id}` (both a hit and a miss), you'll have a much better feel
for what "matches the contract" even means before you try to encode it as
assertions.
