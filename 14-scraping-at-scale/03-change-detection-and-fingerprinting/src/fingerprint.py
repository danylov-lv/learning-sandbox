"""s13.t03 -- stable content fingerprint that excludes the volatile nonce.

The target embeds a fresh random `uuid4` nonce in EVERY response, encoded
differently depending on where it came from:

  GET /product/{id}?day=D&v=1  (classic-div) : <meta name="x-nonce" content="...">
  GET /product/{id}?day=D&v=2  (microdata)    : <!-- nonce:... -->  (HTML comment)
  GET /product/{id}?day=D&v=3  (jsonld)       : <span class="hidden-nonce"
                                                  style="display:none">...</span>
  GET /product/{id}?day=D&v=4  (data-island)  : "nonce" key inside the
                                                  <script id="__DATA__"> JSON block
  GET /api/product/{id}?day=D  (JSON)         : top-level "_nonce" key

`?v=` is not required to reach any of these -- absent `v`, each product's
markup version is a fixed `1 + (product_id % 4)`, so a plain crawl over many
products already exercises all four encodings. Two fetches of the SAME
`?day=` for the SAME unchanged product are byte-identical except for this
one field. A fingerprint that hashes the raw response verbatim will flag
every page as "changed" on every single request -- useless for incremental
re-scraping.

Nothing here talks to the network. `build_fingerprint_index` /
`changed_between` in `detect.py` own the actual fetching; this module only
turns whatever they hand it into a stable digest.
"""


def fingerprint(payload):
    """Return a stable fingerprint (a string, e.g. a hex digest) of one
    product's OBSERVABLE data, with the volatile nonce excluded.

    `payload` is whatever your own fetch layer decides to pass in -- either
    the raw response body (HTML text from `GET /product/{id}`, or JSON text
    / a parsed dict from `GET /api/product/{id}`) or a dict of fields you
    have already extracted from it (price, currency, in_stock, title,
    description, review_count, ...). Either is a valid design; document
    which one you chose with a comment directly above this function, since
    `detect.py` must hand you a matching shape.

    Hard requirement, independent of which shape you pick: calling this
    function twice on two SEPARATE fetches of the same `?day=` of the same
    UNCHANGED product MUST return the identical string, even though every
    such fetch carries a fresh random nonce (see module docstring for where
    it hides in each of the 4 markup versions and in the JSON API). Any
    residual nonce leakage into the hash breaks that guarantee and makes
    every page look changed on every request.

    Conversely, if the underlying product data genuinely changed (price or
    in_stock, per this module's day-over-day overlay), the fingerprint MUST
    differ. Whitespace/formatting differences that carry no information
    (e.g. how you serialize a dict before hashing) should not, by
    themselves, cause a false "changed" -- pick a canonical representation
    and stick to it.
    """
    raise NotImplementedError
