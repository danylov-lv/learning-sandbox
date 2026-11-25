"""t02 -- structured extraction from selector-hostile HTML.

The task: given one raw HTML snippet describing a single product listing,
recover five structured fields -- `name`, `brand`, `price`, `currency`,
`in_stock` -- using an LLM as the parser instead of a CSS-selector walk.

The 50 snippets in `data/extraction.json` are deliberately hostile to
selector-based scraping: price sometimes lives in a generically-named
`<span class="amt">`, sometimes only appears inside a marketing sentence
with no dedicated price element at all, sometimes lives in a `data-*`
attribute, sometimes is written as integer cents with no decimal point,
and some snippets have unclosed tags a strict parser chokes on. A tolerant
reader -- an LLM given the raw text -- can still recover the fields a
brittle selector chain would miss. That's the lesson: robustness to
markup churn is worth the cost of a model call.

`in_stock` is never truly silent -- every template renders SOME signal for
it (an explicit phrase like "In stock" / "Sold out", a `data-in-stock`
attribute, or the presence/absence of an "Add to Cart" button vs. an
"unavailable" span) -- but the surface form varies snippet to snippet.
"""

from harness.llm import get_client  # noqa: F401


def extract_fields(html: str, client) -> dict:
    """Extract structured product fields from one raw HTML snippet.

    Args:
        html: a single product listing's raw HTML (a string -- may contain
            nested tags, unclosed tags, HTML entities like `&nbsp;`, or
            fields hidden in `data-*` attributes rather than visible text).
        client: an `LLMClient` instance (e.g. from `harness.llm.get_client()`)
            to use for the extraction call. Use `client.generate(...)` with
            `format="json"` or a JSON-schema dict to get a parseable
            response -- do not attempt to hand-roll HTML parsing with
            regex/selectors; the point of this task is letting the model
            read the raw text.

    Returns:
        dict with exactly these keys:
          - "name": str -- the product's full display name/title as it
            appears in the snippet (e.g. "Voltix Deluxe monitor A933").
          - "brand": str -- the brand/maker name (e.g. "Voltix").
          - "price": float, or a value `harness.common.norm_price` can
            parse (e.g. a numeric string like "23.93" or "1535" for a
            cents-denominated price -- if a snippet expresses price as
            integer cents in a `data-price-cents` attribute with no
            decimal point anywhere, that value needs converting to a
            decimal currency amount, i.e. divide by 100, before or after
            returning it; the validator parses whatever you return with
            `norm_price`, but it does NOT know to divide by 100 for you).
          - "currency": str -- a 3-letter ISO currency code, e.g. "USD",
            "EUR", or "GBP" (uppercase; the validator uppercases it before
            comparing, but prefer returning it uppercase already).
          - "in_stock": bool -- True if the listing indicates the product
            is currently purchasable, False otherwise. Every snippet
            renders some signal for this (an explicit "in stock" / "sold
            out" style phrase, a boolean-ish `data-in-stock` attribute, or
            an "Add to Cart" button vs. an "unavailable" marker) -- it is
            never left unstated.

    Notes:
        - This function is called once per HTML snippet, so keep the
          prompt self-contained (no cross-snippet state).
        - `temperature=0` is recommended for reproducibility; `client`
          defaults to `temperature=0.0` on `generate`/`chat` already.
        - The model is a 7B instruct model run locally -- design the
          prompt to make the schema and edge cases (cents-as-integer,
          attribute-only fields, prose-only price) explicit rather than
          relying on the model to infer them from a bare "extract this"
          instruction.
    """
    raise NotImplementedError
