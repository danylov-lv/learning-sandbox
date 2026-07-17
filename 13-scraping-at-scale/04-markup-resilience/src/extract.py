"""s13.t04 -- markup-resilience: multi-level fallback extraction.

The target (`GET /product/{id}?v=1..4`) renders the SAME product under 4
different markup encodings, assigned deterministically per product
(`version = 1 + (product_id % 4)`, unless `?v=` overrides it). A crawl over
the real catalog hits all 4 encodings across different products, not one at
a time -- there is no "detect the version once, special-case it" shortcut
that isn't itself a fallback chain: your extractor has to try several
strategies per field, in order, and take the first one that produces a
value, on every single page it's handed.

Fields to extract -- all HTML-visible, in every one of the 4 versions:

    title          str
    price          float
    currency       str    (e.g. "USD", "EUR")
    in_stock       bool
    seller_name    str
    review_count   int
    description    str

Do NOT attempt `rating` or `shipping_info` here. They are JS-only fields --
NEVER present in ANY server-rendered HTML version, only obtainable from the
separate `GET /api/product/{id}` endpoint, which is out of scope for this
task (see task 05 for when paying for that extra fetch is worth it).

`extract_product` is PURE parsing: it takes HTML text you already fetched
and returns a plain dict. No `httpx`/`requests` import belongs in this
module -- no network I/O of its own. That's what makes it trivially
testable and reusable by any fetch layer (task 01's crawler, the task 07
capstone, ...).

Each of the 4 markup versions encodes every field differently -- different
CSS class names, some fields only as `itemprop` microdata, some only inside
a `<script type="application/ld+json">` block, some only inside a
`<script id="__DATA__" type="application/json">` island, and at least one
version puts machine-readable and human-visible price text in DIFFERENT
formats on the SAME page. A selector chain that only knows one of these
shapes will silently return None for most fields on the versions it doesn't
handle -- that silent failure is exactly the bug this task exists to make
visible and then fix. See hints/ for the concrete list of sources to check
and in what order; no ready-made selector code is given there.
"""


def extract_field(html: str, field: str):
    """Optional helper: extract a single named field (one of the keys
    documented on `extract_product`) from `html` using whatever ordered
    fallback chain you build for it (e.g. primary CSS selector -> alternate
    CSS selector -> microdata `itemprop` -> JSON-LD block -> `__DATA__`
    island -> regex last resort). Not called directly by the validator --
    `extract_product` is the graded entrypoint. Provided as a suggested
    decomposition; reshape or drop it if your own structure differs.
    """
    raise NotImplementedError


def extract_product(html: str, product_id: int) -> dict:
    """Extract the HTML-available fields for one product detail page.

    Parameters
    ----------
    html : str
        The raw response body of `GET /product/{product_id}?...` -- ANY of
        the 4 markup versions (classic-div, microdata, jsonld, data-island).
        This function must work correctly on all 4 without being told in
        advance which one it was handed -- that's the whole point.
    product_id : int
        The id the HTML was fetched for. Not required to extract anything
        (every field below is derivable from `html` alone), but available
        in case a fallback path finds it useful as a sanity check.

    Returns
    -------
    dict with exactly these keys:
        title         str
        price         float
        currency      str
        in_stock      bool
        seller_name   str
        review_count  int
        description   str

    A field your fallback chain genuinely cannot find should be `None`
    (never raise, never silently substitute a wrong type or a guessed
    value). On a well-formed page -- i.e. not one of the deliberately
    malformed "bad records" from task 02 -- every field above IS present
    somewhere in the HTML, in all 4 versions; a `None` here on a clean
    record means your fallback chain is incomplete, not that the data
    doesn't exist on the page.
    """
    raise NotImplementedError


def field_completeness(records: list[dict]) -> dict:
    """Optional monitoring helper for your own use while developing: given
    a list of dicts shaped like `extract_product`'s return value, compute
    per-field non-null coverage, e.g. {"title": 1.0, "price": 0.97, ...}.
    The validator computes completeness/correctness against ground truth
    itself and does not call this -- it exists purely so you can watch your
    own fallback chain's coverage as you build it out.
    """
    raise NotImplementedError
