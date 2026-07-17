"""s13.t07 -- day-over-day change detection on top of the capstone pipeline
(task 03's concept, reapplied here on top of `pipeline.py`'s own extraction
instead of the raw `/api/product/{id}` JSON body task 03 worked from).

A useful design note, not a requirement: if `fingerprint()` hashes the dict
`pipeline.extract_fields()` returns (rather than a raw response body), the
volatile nonce never enters the picture at all -- `extract_fields` never
extracts it in the first place, because it isn't one of the seven fields
that function returns. That doesn't make nonce-awareness optional, though:
whatever `payload` shape you actually choose to hash must still exclude any
per-request noise, and you must be able to explain (in DESIGN.md) exactly
why the shape you picked can't leak the nonce in.

`build_fingerprint_index` and `changed_between` fetch via
`pipeline.fetch_product_html` + `pipeline.extract_fields` -- no separate
fetch layer here. Both must stay within this module's politeness budget
(token bucket capacity=25, refill_per_sec=50.0, banned after 25 cumulative
rate-limit violations, honeypot hit = instant ban, browser-like headers
required) and must never touch a honeypot id or `/trap/*`. Getting banned
mid-run is a hard failure: a banned client gets 403 for the rest of the
run, which would make every remaining product look "changed" (or
unreadable) for the wrong reason.

`product_ids=None` means "all real product ids" (`harness.common.
load_catalog`). Where you persist a fingerprint index between runs is up to
you -- a gitignored `run/` directory next to this file (e.g.
`run/fingerprints-day{N}.json`) is reasonable; nothing shared reads or
writes it. Persistence is a valid optimization, not a correctness
requirement: `changed_between` re-fetching both days fresh on every call is
equally correct, just not incremental.
"""


def fingerprint(payload) -> str:
    """Return a stable fingerprint (e.g. a hex digest) of one product's
    OBSERVABLE data, with any volatile per-request noise excluded.

    `payload` is whatever `build_fingerprint_index`/`changed_between`
    decide to hand this function -- most naturally the dict
    `pipeline.extract_fields()` returns for one product, but any shape is
    valid as long as it is genuinely free of per-request noise. Document
    which shape you chose with a comment directly above this function.

    Hard requirement: calling this twice on two SEPARATE fetches of the
    same `?day=` of the same UNCHANGED product must return the identical
    string. If the underlying product data genuinely changed (price or
    in_stock, per this module's day-over-day overlay), the fingerprint
    MUST differ. Pick one canonical serialization and stick to it --
    incidental formatting differences must never cause a false "changed".
    """
    raise NotImplementedError


def build_fingerprint_index(day, client_id, product_ids=None, chaos: bool = False) -> dict:
    """Fetch + extract + fingerprint() each product in `product_ids`
    (default: every real product id) for `day`, using `client_id` as the
    X-Client-Id for every request this call makes.

    Return `{product_id: fingerprint_string}` -- the state a real
    incremental run persists between days.

    Must not fetch honeypot ids or anything under /trap/. Must not exceed
    this module's rate-limit budget for a well-paced client -- getting
    this client banned mid-index-build is a failure mode, not just slow.
    """
    raise NotImplementedError


def changed_between(day_prev, day_curr, client_id, product_ids=None, chaos: bool = False) -> set:
    """Return the set of product ids whose fingerprint differs between
    `day_prev` and `day_curr`, for `product_ids` (default: all real
    product ids), using `client_id` as the X-Client-Id for every request
    this call makes.

    Typical implementation: build (or reuse an already-persisted)
    fingerprint index for `day_prev`, build one for `day_curr`, and return
    the ids where the two disagree.

    Must be nonce-robust and idempotent: calling this function twice in a
    row with the same arguments (simulating a resumed/interrupted run)
    must return the exact same set both times -- no drift, no duplicates,
    no partial state left over from the first call that corrupts the
    second. Must not get this client banned.
    """
    raise NotImplementedError
