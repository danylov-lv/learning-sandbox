# 05 -- Scraping economics: budget router

## Backstory

Somebody on your team ran the numbers and panicked: "if we headless-render
every product page to get ratings and shipping info, our scrape of the full
catalog costs 8x what a plain HTML crawl costs. At scale that's real money."
The knee-jerk fix is "then never render" -- but that silently drops
`rating`/`shipping_info` for every product that actually has them, and a
downstream team that depends on that data notices immediately.

The right fix isn't "render everything" or "render nothing" -- it's "render
only the products where it actually buys you something." A product with
zero reviews has no `rating` to show and (in this catalog) no populated
`shipping_info` either -- rendering it is pure wasted cost. A product with
reviews needs the render, or its record is incomplete. The trick is that
you don't have to guess which is which: the review count itself is sitting
right there in the cheap HTML page you already fetched. This task has you
build that decision into a router and prove, with a modeled cost number (not
wall-clock time), that it hits a completeness target for a fraction of what
rendering everything costs.

## What's given

- The same hostile target as the rest of this module (`docker compose up`,
  port 8313) -- header gate, honeypots, a token-bucket rate limiter with
  bans. `GET /product/{id}` is the cheap HTML fetch. `GET /api/product/{id}`
  is the documented stand-in for a headless render step: it returns the
  full record PLUS `rating` and `shipping_info`, the two fields that never
  appear in any HTML markup version.
- `src/costmodel.py` -- the modeled cost constants (`HTTP_COST`,
  `API_EXTRA_COST`, `RENDER_COST`, `COMPLETENESS_TARGET`) and two small
  arithmetic stubs (`estimate_cost`, `project_per_million`) you fill in.
  The constants are given (public modeled units, not something you derive
  by probing the target); the arithmetic and, more importantly, the
  routing *decision* are yours.
- `src/router.py` -- `scrape_with_budget(product_ids, client_id, day=0)`,
  the entrypoint, currently `raise NotImplementedError`.
- `ANALYSIS.md` -- an unfilled template for the written cost-per-1M-pages
  analysis this task also asks for.
- `tests/validate.py` -- the independent validator (see below).

## What's required

**`src/router.py`**: implement `scrape_with_budget`. For every product id:

1. Always `GET /product/{id}?day=day` (the cheap fetch). Extract at least
   `review_count` from the HTML -- it is visible in every one of this
   target's 4 markup versions (never JS-only), just encoded differently
   per version. Reuse the same fallback-chain extraction idea as task 04
   (markup-resilience): try each version's shape, don't special-case "the
   version I happen to be looking at right now" since the same crawl hits
   all 4 across different products.
2. Only if `review_count > 0`, also `GET /api/product/{id}?day=day` (the
   render step) to fill in `rating`/`shipping_info`. If `review_count ==
   0`, skip the render call entirely for that product.
3. Return one record per product id with the fields the docstring in
   `src/router.py` spells out. A product you didn't render must have
   `rating`/`shipping_info` left `None` -- don't fabricate them just to
   look complete.

The client must not get banned over the course of a full-catalog run: send
a browser-like `User-Agent`/`Accept-Language`, never touch a hidden/
`rel="nofollow"` link, and pace your dispatch rate -- bounded concurrency
alone is not pacing on this target (request handling is sub-millisecond, so
an unpaced burst blows through the rate limiter's token bucket almost
instantly). A full-catalog run here is roughly 4,000 HTML fetches plus
~1,200 render calls; paced sensibly it takes under two minutes.

**`src/costmodel.py`**: implement `estimate_cost(n_products, n_rendered)`
and `project_per_million(n_products, n_rendered)` per their docstrings --
both are pure arithmetic, no network involved.

**`ANALYSIS.md`**: fill in the template -- your cost model assumptions, a
per-1M-pages cost table for all-HTTP / all-render / mixed strategies (use
`project_per_million` to compute the numbers), a short section on when
rendering is and isn't worth it, and a recommendation.

## Completion criteria

```bash
uv run python tests/validate.py
```

This is a real full-catalog run against the live target (~5,200 requests,
paced, roughly 60-120 seconds) -- it is not a fast test, don't run it
repeatedly while iterating on small changes; get the extraction and routing
logic working against a handful of ids first (e.g. by calling
`scrape_with_budget` on a short id list from a scratch script) before
running the full validator.

`tests/validate.py`:

- checks `costmodel.estimate_cost`/`project_per_million` against known
  values first (cheap, fails fast before any network traffic);
- resets a fresh client and calls `scrape_with_budget` over every real
  product id;
- asserts the client never got banned, never hit a honeypot, never got
  header-rejected;
- computes completeness independently from `data/catalog.json`
  (`review_count > 0` products must come back with non-null
  `rating`/`shipping_info`) and requires it to meet the `0.98` target;
- **derives** the total modeled cost from the returned records themselves
  (counts a product as "rendered" when both `rating` and `shipping_info`
  are populated) -- it never trusts anything your code reports about its
  own cost -- and requires that cost to be well under the "render
  everything" cost and in the sensible neighborhood of a reference "mixed"
  strategy cost, with a bound on how much it over-renders products that
  didn't need it;
- samples non-JS fields (title, price, currency, review_count) against the
  catalog for a sample of non-defective ids;
- checks `ANALYSIS.md` is actually filled in (required sections present,
  no leftover placeholder text, a real per-1M-pages table).

Prints `PASSED` with the achieved completeness, render count, and derived
cost, or `NOT PASSED: <reason>` and exits 1.

## Estimated evenings

2

## Topics to read up on

- Cost-aware scraping / crawl budgeting
- HTML extraction fallback chains across heterogeneous markup
- Token-bucket rate limiting from the client side (pacing, not just
  bounding concurrency)
- Amortized cost modeling (per-request vs. per-page-need cost)

## Off-limits

`.authoring/design.md` (at the module root) holds the target site's full
defense/rendering/cost-model contract, the RNG draw order, and the
committed ground-truth values -- spoilers for this and every other task in
the module. Don't read it before finishing this task. `data/catalog.json`
and `data/target-spec.json` are the target's own backend data (not a task
scaffold) -- reading them ahead of time trivializes the extraction and
routing decisions this task is about. Only `data/ground-truth.json` is
committed and meant to be readable.
