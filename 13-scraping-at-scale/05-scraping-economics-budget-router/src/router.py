"""s13.t05 -- the budget router itself.

Rendering a product (calling `GET /api/product/{id}` on top of the html
fetch) is the only way to get `rating`/`shipping_info` -- they are JS-only
fields, absent from every markup version of `GET /product/{id}`. But a
product's `rating`/`shipping_info` only matter for that product's
completeness score when it actually HAS reviews (`review_count > 0`) --
and `review_count` itself is HTML-visible on every markup version (it's a
plain visible number, just encoded differently per version -- see the
target app's `_render_v1..v4` shapes, or work it out yourself the way task
04 does). That is the entire trick: read `review_count` from the cheap html
fetch you already made, and only pay the render step when it's actually
going to buy you something.

You will need an HTML extractor that survives all 4 markup versions for at
least `review_count` (and, if you want the non-JS sample fields right too,
`title`/`price`/`currency`) -- reuse the same fallback-chain selector idea
as task 04 (markup-resilience): try each version's shape in turn, don't
special-case "today's version" since the SAME crawl hits all 4 across
different product ids.

You also need to not get the client banned: send a browser-like
`User-Agent`/`Accept-Language` on every request, never follow a hidden/
`rel="nofollow"` link, and pace your dispatch rate under the target's
refill rate rather than firing everything at once (see this task's README
and, if you've done it, task 01's recon for the shape of a polite client --
bounded concurrency alone is not pacing on this target).
"""


def scrape_with_budget(product_ids, client_id, day=0):
    """Scrape every id in `product_ids` using a two-tier budget strategy and
    return one record (dict) per id.

    For each product id:
      1. ALWAYS `GET /product/{id}?day={day}` (the cheap html fetch -- this
         is `costmodel.HTTP_COST` in the cost model). Extract at least
         `review_count` from the html (all 4 markup versions render it
         somewhere -- it is never JS-only).
      2. IF the extracted `review_count > 0`, ALSO `GET /api/product/{id}?
         day={day}` (the render step -- the ADDITIONAL
         `costmodel.API_EXTRA_COST`) to obtain `rating` and
         `shipping_info`. If `review_count == 0`, do NOT call the render
         endpoint for that product -- nothing js-only is required, and
         calling it anyway is pure wasted cost.

    Send requests under `client_id` (set an `X-Client-Id` header with this
    value on every request) so the target's per-client rate-limit/ban state
    is scoped to this run, and pace your dispatch so the client is never
    banned over the course of the full run.

    Return a list of dicts, one per id in `product_ids`, each with at
    least:
        {
          "id": int,
          "title": str | None,
          "price": float | None,
          "currency": str | None,
          "in_stock": bool | None,
          "review_count": int,
          "rating": float | None,        # populated IFF you rendered this product
          "shipping_info": dict | None,  # {"free","eta_days","carrier"}, populated IFF rendered
        }

    A product you decided NOT to render must have `rating`/`shipping_info`
    left `None` -- do not fabricate them. The validator counts a product as
    "rendered" exactly when both are populated, and derives the total
    modeled cost from that count, never from anything this function reports
    about itself.
    """
    raise NotImplementedError
