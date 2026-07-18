"""t03 -- classification and enrichment: closed-set category classification
plus brand extraction from a deliberately diluted-signal title/description
pair, using a local LLM as a zero/few-shot classifier.

Context: `data/classification.json` holds 80 records, each
`{record_id, title, description}`. Every record's title was built from a
real catalog product, but the generator diluted the signal on purpose:

  - 30% of titles use a brand token drawn from a shared, category-agnostic
    "generic brand" pool instead of a brand that hints at the category
    (e.g. "Zenmark" tells you nothing about whether the product is
    electronics or garden gear).
  - 25% of titles borrow their noun token from a DIFFERENT category's noun
    list (a "cross-category noun" -- e.g. a garden-category record whose
    title contains "webcam", an electronics noun).
  - 30% of descriptions append an off-topic sentence like "Popular among
    streetwear fans this season" naming an unrelated category's activity.

None of these signals are lies about the record's TRUE category -- they are
noise layered on top of it. A keyword/lookup classifier (match brand ->
category, or noun -> category) will be fooled by a meaningful fraction of
these 80 records. An LLM given the record's text plus the closed category
list and asked to reason about the product as a whole should do
substantially better -- that contrast is the point of this task.

Compare this to module 14's TF-IDF + classical classifier over a similarly
diluted signal: here you have no training data and no feature engineering
at all -- one call to a 7B instruct model, zero/few-shot, is the entire
pipeline.

CATEGORIES is the closed label set. It is EXACTLY the same 8 categories
used throughout this module's catalog; `classify_record` must never return
anything outside this list. The category list must be given to the model
explicitly in the prompt -- do not rely on the model already "knowing" a
project-specific label set.
"""

CATEGORIES = [
    "electronics",
    "home-goods",
    "kitchen",
    "toys",
    "sporting-goods",
    "apparel",
    "books",
    "garden",
]


def classify_record(title: str, description: str, client) -> dict:
    """Classify one record's category (closed set) and extract its brand.

    Args:
        title: the record's title string, e.g.
            "Threadloom Premium wool-scarf Q361".
        description: the record's short marketing-sentence description,
            e.g. "One of the premium picks in this year's lineup."
        client: an `harness.llm.LLMClient` instance (e.g. from
            `harness.llm.get_client()` / `harness.common.require_client()`)
            -- use its `generate` (or `chat`) method to call the model.
            Do not construct a provider-specific client directly; only use
            the methods `LLMClient` exposes, so this function keeps working
            unchanged if the module is later pointed at a different
            provider.

    Returns:
        dict with exactly two keys:
          - "category": str, EXACTLY one of the 8 strings in `CATEGORIES`
            above (case and whitespace do not matter to the validator, but
            the value must map unambiguously to one of the 8 -- an
            unrecognized or missing category is scored as wrong, not
            excused).
          - "brand": str, the brand token as it literally appears in
            `title` (e.g. "Threadloom"). The generator sometimes draws the
            brand from a category-agnostic "generic brand" pool instead of
            a category-specific one -- extract whatever brand token is
            actually present in the title either way; do not try to guess
            or "correct" it toward a category-appropriate brand.

    Design notes (yours to make, not prescribed):
      - The prompt must state the closed category list explicitly -- the
        model has no other way to know this project's exact label set.
      - Use `temperature=0` for reproducibility.
      - Consider `format="json"` (or a JSON-schema `format` dict) on
        `client.generate`/`client.chat` to get parseable structured output
        instead of free text you have to regex out.
      - Handle a malformed/non-JSON model response defensively: this
        function must return the dict shape described above (or raise) on
        every call the validator makes across all 80 records, not just the
        easy ones. A response that doesn't parse should not crash the
        entire validator run.
    """
    raise NotImplementedError
