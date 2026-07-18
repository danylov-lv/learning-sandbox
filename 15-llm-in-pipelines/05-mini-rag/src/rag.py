"""t05 -- mini retrieval-augmented generation over the sandbox's own docs.

The task: given a handful of handbook markdown docs (`data/corpus/*.md`),
build a small RAG pipeline -- chunk the docs, embed the chunks, retrieve the
top-k chunks for a question by embedding similarity, then have the model
answer the question grounded in what was retrieved, citing which doc(s)
the answer came from.

Three functions, called in sequence by the validator:

  1. `build_index(docs, client)`  -- chunk + embed once, up front.
  2. `retrieve(index, question, client, k)`  -- per question, cheap.
  3. `answer(question, retrieved, client)`  -- per question, one generate call.

`docs` is a list of dicts, each at least `{"doc_id": str, "text": str}`
(optionally also `"title"` and `"path"`) -- one entry per handbook doc. Get
this list either by calling `generate.build_rag_corpus(SEED)` and taking
the `docs` half of its `(docs, qa)` return (simplest -- see the module's
`generate.py`), or by reading `data/corpus/*.md` yourself and using each
file's stem as `doc_id`. Either source gives you the same six docs.
"""

from harness.llm import cosine, get_client  # noqa: F401


def build_index(docs: list[dict], client) -> object:
    """Chunk every doc and embed the chunks. Runs once, before any question.

    Args:
        docs: list of dicts, each at least `{"doc_id": str, "text": str}` --
            one entry per handbook doc (see module docstring above for how
            to obtain this list).
        client: an `LLMClient` (e.g. `harness.llm.get_client()`). Use
            `client.embed(texts: list[str]) -> list[list[float]]` to embed
            chunk texts -- one batched call across all chunks is far cheaper
            than one call per chunk, though either works.

    Returns:
        An index: any object you like (list, dict, dataclass, ...) that you
        also consume in `retrieve` below. The one hard requirement is that
        every chunk you put into it retains its source `doc_id` -- whatever
        shape you choose, `retrieve` must be able to report, for each chunk
        it returns, which doc that chunk came from. `answer`'s citations
        rely on this downstream.

    Notes:
        - Chunking strategy is your call: fixed-size character/token
          windows, paragraph splits, sentence groups, whole documents as a
          single "chunk" -- there is no prescribed granularity. A doc that
          is chunked into pieces small enough to be topically focused
          retrieves more precisely than one treated as a single blob, but
          the exact scheme is a design choice, not a checked contract.
        - Do not embed anything inside `retrieve` or `answer` that could
          instead be embedded once here -- the chunk embeddings should not
          be recomputed per question.
    """
    raise NotImplementedError


def retrieve(index: object, question: str, client, k: int) -> list[dict]:
    """Return the top-k chunks most relevant to `question`, by embedding
    similarity.

    Args:
        index: whatever `build_index` returned.
        question: the natural-language question to answer.
        client: an `LLMClient`. Embed the question with
            `client.embed([question])[0]` and rank chunks against it with
            `harness.llm.cosine(a, b)` (imported above).
        k: how many chunks to return.

    Returns:
        list[dict], length <= k, ordered most-relevant first. Each dict
        must expose at least:
          - "doc_id": str -- the source doc this chunk came from (must
            match one of the `doc_id` values in the `docs` passed to
            `build_index`).
          - "text": str -- the chunk's text (whatever `answer` needs to
            ground its response).
        Extra keys (e.g. a similarity score) are fine.
    """
    raise NotImplementedError


def answer(question: str, retrieved: list[dict], client) -> dict:
    """Generate an answer to `question`, grounded in `retrieved`, citing
    the source doc(s).

    Args:
        question: the natural-language question.
        retrieved: the list returned by `retrieve` -- the chunks to ground
            the answer in. Do not call `retrieve` again here; use exactly
            what was passed in.
        client: an `LLMClient`. Use `client.generate(...)` (or `.chat(...)`)
            with a prompt that includes the retrieved chunk text as context
            and instructs the model to answer only from that context.

    Returns:
        dict with exactly these keys:
          - "answer": str -- the generated answer text.
          - "citations": list[doc_id] -- the `doc_id`(s) (from `retrieved`)
            the answer draws on. At minimum, include every distinct
            `doc_id` present in `retrieved`, or narrow it down to the
            specific chunk(s) actually used -- either is acceptable, but
            citations must be drawn from `retrieved`'s `doc_id`s, not
            invented.

    Notes:
        - `temperature=0` is recommended for reproducibility; `client`
          defaults to `temperature=0.0` on `generate`/`chat` already.
        - Keep the prompt explicit about grounding: tell the model to
          answer using only the provided context, and to say so if the
          context doesn't contain the answer, rather than inventing one.
    """
    raise NotImplementedError
