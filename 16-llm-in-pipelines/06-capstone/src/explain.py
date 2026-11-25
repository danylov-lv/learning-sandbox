"""t06 capstone -- RAG "explain this product" step.

Given a question about a specific product, retrieve the most relevant
catalog entries (rendered to short text documents) via embedding
similarity, then ask the model to answer using only that retrieved
context, citing which product(s) it drew from.

This reuses t05's retrieve-then-generate shape but points it at the
pipeline's own product catalog instead of the "Sandbox Handbook" corpus
`harness`/t05 use -- "explain this product" is a question about a product
record (name, brand, category, price, specs...), not about the sandbox's
own conventions docs.
"""

from harness.llm import cosine  # noqa: F401


def render_catalog_doc(product: dict) -> str:
    """Render one catalog record into a short text document for retrieval
    -- the unit `explain_product` embeds and searches over.

    Args:
        product: a dict with at least `{product_id, name, brand, category,
            price, currency, in_stock}`, and typically also `{specs:
            {color, material, weight_kg, warranty_years}}` -- the shape
            `generate.build_catalog` produces, and the shape of
            `run_pipeline`'s enriched catalog records.

    Returns:
        A single string covering every field above (prose or `key: value`
        lines, your choice) -- specific enough that embedding it and
        matching against a question like "what color is product 42" or
        "is the Voltix Deluxe monitor A933 in stock" retrieves the right
        document over unrelated decoys in the same candidate set.
    """
    raise NotImplementedError


def explain_product(question: str, catalog: list, client) -> dict:
    """Answer a question about a product by retrieving relevant catalog
    entries and generating a grounded answer.

    Args:
        question: a natural-language question about a product, e.g. "What
            brand is product 42?" or "Is the Voltix Deluxe monitor A933 in
            stock?".
        catalog: list of product dicts (see `render_catalog_doc`) to
            search over -- may be the full catalog or a smaller candidate
            set the caller has already narrowed down.
        client: an `LLMClient`. Use `client.embed(...)` for retrieval and
            `client.generate(...)` / `client.chat(...)` for the answer.

    Returns dict with exactly these keys:
        "answer": str -- a natural-language answer grounded in the
            retrieved catalog entries, not the model's own guesswork.
        "citations": list -- the `product_id` value(s) of the catalog
            entries actually used as evidence, most-relevant first, at
            least one entry when `catalog` is non-empty.

    Retrieval: embed every candidate in `catalog` via `render_catalog_doc`
    + `client.embed`, embed `question` the same way, rank candidates by
    cosine similarity (`harness.llm.cosine`), and use only the top few as
    generation context -- don't hand the entire candidate set to the model
    as context; that defeats the point of retrieval and risks producing an
    unfocused or wrong answer when the candidate set contains
    lookalike decoys.
    """
    raise NotImplementedError
