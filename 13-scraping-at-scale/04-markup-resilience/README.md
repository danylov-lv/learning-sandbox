# 04 -- Markup resilience

## Backstory

The scraper you wrote in task 01 fetches product pages just fine. Then
someone points it at the *rest* of the catalog and completeness quietly
craters -- prices go missing on a third of products, seller names on
another chunk, stock status somewhere else. Nothing errored. Nothing
logged a warning. Your selector-based extractor just returned `None` for
every field it couldn't find, and moved on like nothing happened.

The catalog didn't get corrupted. It's rendered through four different
templates, and which one a given product gets is baked into the product,
not the day or the request. Some products are plain, descriptively-classed
`<div>`s. Some use `schema.org` microdata. Some hide the price entirely
inside a `<script type="application/ld+json">` block with no visible price
text anywhere on the page. Some ship a minimal HTML shell and leave the
real data sitting in a `<script id="__DATA__">` island, like a single-page
app's hydration payload that never got stripped out. Any one of these is a
completely normal thing for a real e-commerce site to do (redesigns roll
out gradually, different teams own different templates, structured-data
markup gets added incrementally) -- a scraper that only understands one of
them is a scraper that silently degrades the moment it meets any of the
others.

You are not going to detect which template a page uses and special-case
it. You're going to build extraction that doesn't need to know.

## What's given

- `src/extract.py` -- `extract_product(html, product_id) -> dict` and
  `extract_field(html, field)` stubs, both `raise NotImplementedError` with
  full docstrings covering the required fields and the four encodings.
  A `field_completeness(records) -> dict` stub is also provided as an
  optional helper for your own monitoring while you build the chain (the
  validator does not call it).
- The live target (`docker compose up`, port 8313) serving
  `GET /product/{id}?v=1..4&day=0` -- `v` forces a specific markup version
  so you can develop and test against each encoding directly, without
  relying on whichever version a given product's id happens to default to.
- `harness/common.py`'s `TargetClient` for talking to the target politely
  (browser-like default headers, a per-instance `X-Client-Id`) -- it does
  no parsing; that part is entirely yours.

## What's required

Implement `extract_product(html: str, product_id: int) -> dict` in
`src/extract.py` so that it correctly returns these seven fields regardless
of which of the four markup versions the HTML was rendered as:

```
title          str
price          float
currency       str
in_stock       bool
seller_name    str
review_count   int
description    str
```

`extract_product` is pure parsing -- it takes HTML text you (or the
validator) already fetched and returns a dict; it does not fetch anything
itself. Build real fallback chains per field: try a primary source, then an
alternate, then another, until one succeeds or you're out of options. A
field that's genuinely absent should be `None`, never a guess.

Do not attempt `rating` or `shipping_info` -- they are JS-only fields, never
present in any server-rendered HTML version on this target, regardless of
markup encoding. They only exist behind `GET /api/product/{id}`, which is
out of scope here (see task 05, where fetching that extra endpoint is
modeled as a real, non-trivial cost).

## Completion criteria

Run from the **module root** (`13-scraping-at-scale/`), not this task
directory:

```bash
uv run python 04-markup-resilience/tests/validate.py
```

The validator drives the LIVE target directly (never trusting your own
extractor's output as ground truth): it samples ~200 clean product ids
spread across every `id % 4` residue, fetches each one under all four
explicit markup versions (`?v=1..4&day=0`, ~800 requests total, paced
politely well under the target's rate limit), calls your
`extract_product`, and compares every field against `data/catalog.json`'s
true values (price within 0.01, description whitespace-normalized, the
rest exact).

It computes a per-version score (fraction of field checks correct, for
each of v1..v4) and an overall score across all four combined. You pass
only if the **overall score is >= 0.98 AND no single version's score is
below 0.95** -- a chain that handles three of the four encodings well and
silently fails the fourth does not pass, even if its average looks fine.
On failure it names the specific version and field that's weakest, with an
example of what your extractor returned vs. what was expected.

## Estimated evenings

2

## Topics to read up on

- `schema.org` microdata (`itemprop`, `itemscope`, `itemtype`) vs. JSON-LD
  vs. Open Graph -- the structured-data conventions real sites mix and
  match
- CSS selectors vs. XPath for HTML extraction, and when one expresses a
  fallback more naturally than the other
- Defensive parsing / fallback-chain design (try-in-order extraction,
  never raising on a missing field)
- Type coercion at extraction boundaries (string vs. number vs. boolean
  fields arriving in inconsistent shapes across sources)

## Off-limits

`.authoring/design.md` (at the module root) documents the exact HTML each
markup version renders, the target's full defense/behavior contract, and
the committed ground-truth values -- reading it before finishing this task
defeats the exercise (you'd be told exactly what each template looks like
instead of discovering it). Read it after, if at all.
