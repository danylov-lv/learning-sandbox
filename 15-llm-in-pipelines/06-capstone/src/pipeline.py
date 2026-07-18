"""t06 capstone -- end-to-end enrichment pipeline.

Composes the module's three data-shaping skills (extraction, classification
+ enrichment, embedding-dedup) into one pipeline with a quality/confidence
gate that routes unreliable records to a quarantine bucket instead of the
clean catalog.

`extract_record` and `classify_record` are single-item functions (called
once per HTML snippet / title+description pair) that must NEVER raise --
they self-assess their own reliability and return a low-confidence,
invalid record instead of propagating a parse failure. `dedup_cluster`
clusters a whole batch of title variants at once (clustering is inherently
a batch operation, unlike the other two). `run_pipeline` wires all three
together and applies the gate.

This mirrors t02 (structured-extraction), t03 (classification-and-
enrichment), and t04 (embedding-dedup) in spirit, but every function here
has an extra responsibility those tasks don't: staying resilient to
malformed input and garbage model output without crashing the batch, since
a capstone pipeline runs unattended over many records where a small
fraction failing is the normal case, not an exception.
"""

from harness.llm import cosine, get_client  # noqa: F401
from generate import CATEGORIES  # noqa: F401


def extract_record(html: str, client) -> dict:
    """Extract structured product fields from one raw HTML snippet.

    Same underlying task as t02's `extract_fields(html, client)` -- the
    snippet may have price in a generically-named element, in a marketing
    sentence, in a `data-*` attribute, as integer cents, or inside broken/
    unclosed tags -- but this version must ALSO self-assess its own
    reliability and never raise.

    Args:
        html: one raw HTML product listing. May be well-formed, or (for
            CP2's chaos input) truncated/garbled by an upstream scraper
            bug -- possibly missing fields entirely, possibly not even
            valid HTML.
        client: an `LLMClient` (e.g. from `harness.llm.get_client()`).

    Returns dict with exactly these keys:
        "name": str | None -- product name/title as it appears in the
            snippet, or None if it could not be recovered at all.
        "brand": str | None
        "price": float | None -- a parsed number (not a raw price string).
            If the snippet expresses price as integer cents (no decimal
            point anywhere), convert to a decimal amount before returning.
        "currency": str | None -- 3-letter uppercase code ("USD"/"EUR"/
            "GBP") if recoverable.
        "in_stock": bool | None -- True/False if recoverable, None if the
            snippet gives no signal at all (should be rare -- every
            template renders SOME signal, but corrupted/truncated input in
            CP2 may destroy it).
        "confidence": float -- your own estimate in [0.0, 1.0] of how
            reliable this record is. A reasonable approach: start from the
            fraction of the 5 fields above that came back non-empty and
            well-typed, and drop it further (e.g. to 0.0) if the model's
            raw response wasn't valid JSON and you had to fall back to a
            partial parse.
        "valid": bool -- your own gate decision for this record (typically
            `confidence >= some threshold you choose`). Feeds directly into
            `run_pipeline`'s catalog/quarantine routing.

    MUST NOT raise on malformed HTML or a non-JSON / truncated / empty
    model response -- catch the failure internally and return a low-
    confidence, `valid=False` record (unrecoverable fields as None)
    instead. This is exactly what CP2 (chaos) exercises: corrupted input
    and injected garbage model output must degrade to a quarantined
    record, never an unhandled exception that aborts the whole batch.
    """
    raise NotImplementedError


def classify_record(title: str, description: str, client) -> dict:
    """Classify one title/description pair and extract its brand.

    Same underlying task as t03's classification step: `title` and
    `description` deliberately dilute the category signal (a generic,
    category-agnostic brand some of the time; a noun borrowed from a
    different category some of the time; an off-topic marketing clause
    some of the time) -- category has to be inferred from the text as a
    whole, not read off a single token.

    Args:
        title: short product title.
        description: one or two marketing sentences about the product.
        client: an `LLMClient`.

    Returns dict with exactly these keys:
        "category": str | None -- MUST be one of `generate.CATEGORIES`
            (the closed 8-set) if set at all; None if the model's output
            couldn't be mapped into that set.
        "brand": str | None -- the brand token as stated in the title.
        "confidence": float -- your own estimate in [0.0, 1.0]. A
            reasonable approach: 1.0 when `category` is a member of
            `generate.CATEGORIES` and `brand` is a non-empty string, 0.0
            when the model's response wasn't valid JSON / didn't map to a
            real category (a hallucinated category name is exactly the
            kind of failure this should catch).
        "valid": bool -- your own gate decision, typically
            `confidence >= some threshold you choose`.

    MUST NOT raise on a non-JSON / garbled model response -- catch it and
    return a low-confidence, `valid=False`, `category=None` record instead.
    """
    raise NotImplementedError


def dedup_cluster(items: list, client) -> list:
    """Cluster a batch of title variants into product clusters.

    Same underlying task as t04's embedding-dedup step: embed every title
    (`client.embed`) and group titles that refer to the same underlying
    product (abbreviated, reordered, re-punctuated, or brand-repositioned
    variants of one canonical name) into the same cluster, via a cosine-
    similarity threshold or any clustering approach built on top of
    `harness.llm.cosine`.

    Args:
        items: list of `{"item_id": str, "title": str}`.
        client: an `LLMClient`.

    Returns:
        list of dict, ONE ENTRY PER INPUT ITEM, in the SAME ORDER as
        `items`:
            {"item_id": str, "cluster_id": int | str, "confidence": float,
             "valid": bool}
        `cluster_id` only needs to be consistent WITHIN this call's output
        (items in the same true cluster get the same `cluster_id`) -- the
        validator compares cluster AGREEMENT (pairwise F1), not literal
        cluster_id values. `confidence` is your own estimate of how
        reliable this item's cluster assignment is (e.g. its similarity to
        the closest other member of its assigned cluster, or 1.0 for a
        confident singleton). `valid` is your gate decision.

    MUST NOT raise if embedding a single title fails -- fall back to
    putting that item in its own singleton cluster with low confidence
    rather than aborting the whole batch.
    """
    raise NotImplementedError


def run_pipeline(extraction_items: list, classification_items: list, dedup_items: list, client) -> dict:
    """Compose extract_record / classify_record / dedup_cluster into one
    pipeline call, then apply the quality/confidence gate.

    Args:
        extraction_items: list of `{"snippet_id": str, "html": str}`
            (matches `data/extraction.json`'s shape).
        classification_items: list of `{"record_id": str, "title": str,
            "description": str}` (matches `data/classification.json`'s
            shape).
        dedup_items: list of `{"item_id": str, "title": str}` (matches
            `data/dedup.json`'s shape).
        client: an `LLMClient`.

    Returns dict with exactly these keys:
        "extraction": list, one entry per `extraction_items` input, SAME
            ORDER as input -- each entry is `extract_record`'s return dict
            plus `"snippet_id"`.
        "classification": list, one entry per `classification_items`
            input, SAME ORDER as input -- each entry is `classify_record`'s
            return dict plus `"record_id"`.
        "dedup": the list `dedup_cluster` returned (one entry per
            `dedup_items` input, same order, already carrying `item_id`).
        "catalog": list of every record above with `valid=True`, each
            additionally tagged `{"stage": "extraction"|"classification"|
            "dedup", "id": <snippet_id|record_id|item_id>}`.
        "quarantine": list of every record above with `valid=False`, tagged
            the same way plus a short human-readable `"reason"` string
            (e.g. `"price unparseable"`, `"category not in closed set"`,
            `"model response was not valid JSON"`).

    MUST NOT raise -- a single bad record's failure must never abort the
    batch. `extract_record` / `classify_record` / `dedup_cluster` already
    guarantee they don't raise on a bad model response; `run_pipeline`
    itself must not introduce a NEW way to crash on top of that (e.g. an
    unguarded field lookup on a record whose fields came back as `None`).
    Process every item in every stage regardless of how earlier items in
    that stage turned out.
    """
    raise NotImplementedError
