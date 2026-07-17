"""s13.t03 -- change detection entrypoint: fingerprint two day-snapshots of
a product set and report which ids actually changed.

This is the piece an incremental re-scraper runs on a schedule: instead of
re-fetching FULL detail for every product on every run, fetch a cheap
per-product fingerprint for the current day, diff it against the fingerprint
index persisted from the previous run, and only re-fetch (or re-process)
full detail for the ids whose fingerprint moved.

You write your own fetch layer here -- nothing in `harness/` does parsing,
retries, rate-limit backoff, or honeypot avoidance. `harness.common.
TargetClient` is available as a thin `httpx.Client` wrapper (sets a
browser-like `User-Agent`/`Accept-Language` and an `X-Client-Id`) if you
want a starting point, but it has no pacing or backoff of its own -- add
your own bounded concurrency + paced dispatch on top, the same politeness
constraints as every other task in this module (token bucket capacity=25,
refill_per_sec=50.0, banned after 25 cumulative rate-limit violations,
honeypot hit = instant ban, header gate needs a browser User-Agent +
non-blank Accept-Language). Getting banned mid-run is a hard failure here:
a banned client returns HTTP 403 for the rest of the run, which would make
every remaining product look "changed" (empty/decoy body) for the wrong
reason.

`product_ids=None` means "all real product ids" -- 1..n_products from this
module's catalog (see `harness.common.load_catalog`/`load_ground_truth`).
Never fetch an id in the honeypot range (the contiguous block immediately
above n_products) or anything under `/trap/`.

Where you persist state (a fingerprint index from a previous run) is up to
you -- a gitignored `run/` directory next to this file (e.g.
`run/fingerprints-day{N}.json`) is a reasonable place; nothing shared reads
or writes it.
"""


def build_fingerprint_index(day, client_id, product_ids=None):
    """Fetch + fingerprint() each product in `product_ids` (default: all
    real product ids) for the given `day`, using `client_id` as the
    X-Client-Id for every request this call makes.

    Return {product_id: fingerprint_string}. This is the "state" an
    incremental run persists between days -- next run's `changed_between`
    (or a hand-rolled diff against a saved index) compares against it.

    Must not fetch honeypot ids or anything under /trap/. Must not exceed
    the target's rate-limit budget for a well-paced client (see module
    docstring) -- getting this client banned mid-index-build is a failure
    mode, not just slow.
    """
    raise NotImplementedError


def changed_between(day_prev, day_curr, client_id, product_ids=None):
    """Return the set of product ids whose fingerprint differs between
    `day_prev` and `day_curr`, for `product_ids` (default: all real product
    ids), using `client_id` as the X-Client-Id for every request this call
    makes.

    Typical implementation: build (or reuse an already-persisted)
    fingerprint index for `day_prev`, build one for `day_curr`, and return
    the ids where the two disagree -- `{pid for pid in ids if
    idx_prev[pid] != idx_curr[pid]}`. Reusing a stored `day_prev` index
    (instead of re-fetching it) is a valid optimization but not required for
    correctness here.

    Must be nonce-robust: fetching the SAME unchanged product for
    `day_prev` and `day_curr` must NOT appear in the returned set just
    because each fetch carried a different random nonce. Must not get this
    client banned (see module docstring for the politeness budget).
    """
    raise NotImplementedError
