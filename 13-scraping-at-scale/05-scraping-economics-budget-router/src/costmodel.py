"""s13.t05 -- cost-model constants and helpers for the budget router.

These are the MODELED costs the target's cost model is built on (see this
task's README and `.authoring/design.md`'s "Cost model" section, read after
finishing): a plain `GET /product/{id}` html fetch is the cheap baseline; a
`GET /api/product/{id}` call is the deterministic stand-in for a headless
render step and costs substantially more on top of the html fetch you
already paid for that product. Nothing here talks to the network -- this
module is pure arithmetic over counts the caller supplies.

The constants are public modeled units, not something you derive by probing
the target -- they are given. The two functions below are small stubs you
fill in; the actual routing DECISION (which products to render) lives in
`router.py`, not here.
"""

HTTP_COST = 1.0        # GET /product/{id} -- paid for every product, every strategy
API_EXTRA_COST = 7.0   # the ADDITIONAL cost of also calling GET /api/product/{id}
RENDER_COST = HTTP_COST + API_EXTRA_COST  # cost of fully rendering one product (8.0)

COMPLETENESS_TARGET = 0.98


def estimate_cost(n_products, n_rendered):
    """Total modeled cost of scraping `n_products` products, `n_rendered` of
    which (0 <= n_rendered <= n_products) ALSO received the render step
    (`GET /api/product/{id}`) in addition to their html fetch.

    Every product pays `HTTP_COST` exactly once -- the html fetch is never
    skippable, it's how a router learns whether a product even needs
    rendering. Only the `n_rendered` subset pays the additional
    `API_EXTRA_COST` on top of that.

    Returns the total cost as a float. For example, at n_products=4000:
      - n_rendered=0     -> "render nothing" cost
      - n_rendered=4000  -> "render everything" cost
      - n_rendered=1191  -> a mixed strategy's cost
    """
    raise NotImplementedError


def project_per_million(n_products, n_rendered):
    """Project a strategy's cost to a 1,000,000-page run.

    `n_products`/`n_rendered` describe a strategy's OBSERVED render
    fraction (n_rendered / n_products). Scale `estimate_cost(n_products,
    n_rendered)` linearly so the result is what the SAME strategy (i.e. the
    same render fraction) would cost if it were applied across 1,000,000
    products instead of `n_products`.

    Returns the projected cost as a float. Used to fill in this task's
    ANALYSIS.md per-1M-pages table -- see the README.
    """
    raise NotImplementedError
