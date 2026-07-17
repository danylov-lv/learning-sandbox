"""Pandera contract for product records fetched from GET /api/product/{id}.

This is the gate at the extraction boundary: every record a scraper pulls
out of the target's JSON endpoint must pass this schema before it is
allowed to call itself "clean" data. Records that fail go to a quarantine
sink instead of being silently dropped or silently coerced — see gate.py,
which is the other half of this task.

A record (one GET /api/product/{id} response body) looks like this on a
CLEAN product:

    {
      "id": 1, "slug": "deluxe-headphones-1", "url": "/product/1",
      "title": "Deluxe Headphones", "category": "electronics",
      "brand": "Wrenfield", "price": 52.96, "currency": "EUR",
      "in_stock": true, "seller_id": 99, "seller_name": "Solstice Supply Co",
      "review_count": 0, "rating": null,
      "description": "Deluxe Headphones by Wrenfield. ...",
      "shipping_info": {"free": false, "eta_days": 1, "carrier": "ParcelJet"},
      "_nonce": "ac982d52-1a13-42de-a0ab-6f243c348171"
    }

`rating` is legitimately `null` whenever `review_count == 0` — that is NOT
a defect, do not treat it as one. `_nonce` is a fresh random value on every
single request (see the module README) and carries no information at all;
it should never reach the schema. `shipping_info` is a nested object, not a
flat column — decide how you want to represent it (flatten it into a few
scalar columns before validating, or drop it before the boundary check and
handle it separately) before you design the schema around it.

About 10% of records carry a planted defect, always in exactly one of six
shapes (same categories called out in the module README): a missing or
otherwise invalid price (absent key, the literal string "N/A", or a
negative number), an unrecognized currency code (e.g. "XYZ" instead of a
real ISO code), an empty title, or a corrupted/truncated description. The
description-corruption signal is NOT specified here on purpose — go fetch
a modest sample of live records yourself (`GET /api/product/{id}` for a
range of ids; you don't need all 4000 to spot the pattern) and look at what
a corrupted one actually contains before deciding how to detect it. A
"just check if it's short" heuristic will not hold up: normal descriptions
already vary in length.

Fill in build_product_schema() below. The docstring on the function lists
every rule the returned schema needs to express. Nothing here talks to
files or does I/O — that lives in gate.py, which imports this schema and
applies it to a batch of records.
"""

from __future__ import annotations

import pandera.pandas as pa
from pandera.pandas import Column, Check  # noqa: F401  (convenience imports for your schema)

# Currencies this catalog actually uses. Anything else (e.g. "XYZ") is a
# planted defect, not a legitimate code this schema should ever accept.
ALLOWED_CURRENCIES = ["USD", "EUR", "GBP", "CAD"]


def build_product_schema() -> pa.DataFrameSchema:
    """Build and return the pandera DataFrameSchema for a normalized batch
    of product records (one row per record, already flattened to scalar
    columns — see gate.py's normalize step).

    The schema must express, at minimum:

      - Every field is required and has the right dtype: `id` (int),
        `slug`/`url`/`title`/`category`/`brand`/`currency`/`description`
        (str), `in_stock` (bool), `seller_id`/`review_count` (int),
        `price` (numeric), `rating` (numeric, NULLABLE — null is legitimate
        when review_count == 0, do not reject it).
      - `price` must be present (not null — this is what catches
        missing_price and coercion failures like the "N/A" string),
        strictly greater than 0 (catches negative_price), and below a sane
        ceiling — think about what "sane" means when categories span a
        cheap-grocery-item price and a premium-electronics price; a single
        flat number that's generous enough not to reject anything real is
        one valid choice, a per-category map is another. Pick one
        deliberately, don't just skip the rule because nothing in this
        module's planted defects happens to test it directly.
      - `currency` must be one of ALLOWED_CURRENCIES (catches bad_currency).
      - `title` must be non-empty (catches empty_title) — null is also not
        acceptable here, only a real non-blank string counts.
      - `description` must not carry the corruption signal a truncated
        record leaves behind (catches truncated) — see the module
        docstring above: go find one yourself first, then express it as a
        Check.
      - Decide deliberately whether the schema should be `strict` about
        columns it doesn't recognize (i.e. what happens if gate.py hands it
        a DataFrame with an extra column it wasn't told about). There is a
        right default for a boundary contract like this one — think about
        why, then set `strict=` accordingly instead of leaving it at
        pandera's own default.

    Return the DataFrameSchema (do not call .validate() here — that's
    gate.py's job, once per batch, with lazy=True).
    """
    raise NotImplementedError
