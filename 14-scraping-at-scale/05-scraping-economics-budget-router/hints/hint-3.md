Concrete shape, without code.

**Per-product decision flow.** For each id: fetch the HTML page once. Parse
out at least `review_count` (title/price/currency too, if you want the
validator's sample check to also pass cleanly -- it compares those against
the catalog for a handful of ids). If `review_count > 0`, fetch
`/api/product/{id}` and merge its `rating`/`shipping_info` into the record
you're building; otherwise leave those two fields `None` and move on to
the next id. Two fetches in the worst case, one in the common case (~70%
of this catalog has zero reviews) -- that asymmetry is the entire cost
saving.

**Extracting `review_count` across 4 markup versions.** You don't know
which version a given product id will render as ahead of time (it's a
per-product, not per-day, assignment), so don't try to detect-then-branch
on "version 1 vs version 2" as your top-level strategy. Instead build one
extraction function per FIELD that tries several selector/regex shapes in
order and returns the first one that produces a value -- a fallback chain,
not a version switch. `review_count` in particular is always a plain
integer next to (or inside) some element whose text or attributes you can
search regardless of which specific class name or wrapper it's sitting in
this time.

**Not getting banned across ~5,200 requests.** A semaphore that just
bounds concurrency is not enough on this target (it responds in
sub-millisecond time, so an unbounded-rate burst drains the rate limiter's
token bucket almost instantly even with a "reasonable" concurrency
number). You need an explicit pacer that limits your actual dispatch RATE
(requests per second), not just how many are in flight at once -- and
ideally one based on real measured elapsed time between dispatches rather
than trusting a single `sleep()` call's requested duration to be exact.
Send `X-Client-Id: <your client id>` on every request so the target's
rate-limit bucket is scoped consistently to this run instead of drifting
across whatever connection reuse your HTTP client happens to do.

**Projecting to 1M pages (`costmodel.py` / `ANALYSIS.md`).** Once you know
a strategy's cost over `n_products` real products with `n_rendered` of
them rendered, scaling it to 1,000,000 pages is just "hold the render
FRACTION (`n_rendered / n_products`) constant and scale the whole cost up
linearly" -- work out what that means for `estimate_cost`'s two inputs
before you touch `project_per_million`.
