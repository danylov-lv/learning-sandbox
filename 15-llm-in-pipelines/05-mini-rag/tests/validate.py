"""Validator for 15-llm-in-pipelines task 05 -- mini-rag.

Loads the shared "Sandbox Handbook" corpus + QA pairs (`generate.
build_rag_corpus(SEED)`, the same call `generate.py` uses to write
`data/corpus/*.md`) and drives the learner's three functions in
`src/rag.py`:

  1. `build_index(docs, client)` -- once, over all 6 docs.
  2. `retrieve(index, question, client, k=K)` -- once per QA pair.
  3. `answer(question, retrieved, client)` -- once per QA pair.

Two metrics, computed independently from gold pulled straight out of
`build_rag_corpus`'s `qa` list (never from anything the learner's code
wrote to disk):

  - PRIMARY, `hit@k`: fraction of the 15 questions whose `gold_doc_id`
    appears among the `doc_id`s of the top-K chunks `retrieve` returned.
    Deterministic given the embedding model, so this is the trustworthy
    signal -- retrieval via `nomic-embed-text` over a small, topically
    distinct 6-doc corpus should be strong.
  - SECONDARY, answer-fact rate: fraction of the 15 questions where
    `answer(...)["answer"]` contains the question's `gold_answer_substring`
    (case-insensitive) or has enough `gold_keywords` overlap. Generation
    phrasing is noisier than retrieval, so this threshold is lower.

Both thresholds were measured live against `qwen2.5:7b-instruct` +
`nomic-embed-text` with a throwaway reference implementation (paragraph
chunking, cosine top-k, a grounded-answer prompt) and set with headroom
below what that run achieved -- see `.authoring/design.md` for the
measured numbers.

Run from the module root:

    uv run python 15-llm-in-pipelines/05-mini-rag/tests/validate.py
"""

import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))
sys.path.insert(0, str(TASK_ROOT))

from generate import SEED, build_rag_corpus  # noqa: E402
from harness.common import guarded, not_passed, passed, require_client  # noqa: E402
from src.rag import answer, build_index, retrieve  # noqa: E402

K = 3
HIT_AT_K_THRESHOLD = 0.80
ANSWER_FACT_THRESHOLD = 0.55


def _answer_contains_fact(generated_answer: str, gold_answer_substring: str, gold_keywords: list) -> bool:
    text = (generated_answer or "").lower()
    if gold_answer_substring.lower() in text:
        return True
    if not gold_keywords:
        return False
    hits = sum(1 for kw in gold_keywords if kw.lower() in text)
    return hits / len(gold_keywords) >= 0.5


@guarded
def main():
    client = require_client()

    docs, qa = build_rag_corpus(SEED)
    valid_doc_ids = {d["doc_id"] for d in docs}

    index = build_index(docs, client)
    if index is None:
        not_passed("build_index(docs, client) returned None -- expected an index object")

    hits = 0
    fact_hits = 0
    for item in qa:
        question = item["question"]
        gold_doc_id = item["gold_doc_id"]

        retrieved = retrieve(index, question, client, K)
        if not isinstance(retrieved, list) or not retrieved:
            not_passed(f"retrieve(...) for {question!r} must return a non-empty list, got {retrieved!r}")
        for chunk in retrieved:
            if not isinstance(chunk, dict) or "doc_id" not in chunk:
                not_passed(f"retrieve(...) returned a chunk without a 'doc_id' key: {chunk!r}")
            if chunk["doc_id"] not in valid_doc_ids:
                not_passed(
                    f"retrieve(...) returned a chunk with doc_id {chunk['doc_id']!r}, "
                    f"which is not one of the corpus doc_ids {sorted(valid_doc_ids)}"
                )
        if len(retrieved) > K:
            not_passed(f"retrieve(...) returned {len(retrieved)} chunks, more than k={K}")

        retrieved_doc_ids = {chunk["doc_id"] for chunk in retrieved}
        if gold_doc_id in retrieved_doc_ids:
            hits += 1

        result = answer(question, retrieved, client)
        if not isinstance(result, dict) or "answer" not in result or "citations" not in result:
            not_passed(f"answer(...) for {question!r} must return {{'answer', 'citations'}}, got {result!r}")

        if _answer_contains_fact(result["answer"], item["gold_answer_substring"], item["gold_keywords"]):
            fact_hits += 1

    hit_at_k = hits / len(qa)
    answer_fact_rate = fact_hits / len(qa)

    if hit_at_k < HIT_AT_K_THRESHOLD:
        not_passed(
            f"hit@{K} = {hit_at_k:.3f} ({hits}/{len(qa)}), below required {HIT_AT_K_THRESHOLD} -- "
            f"retrieve(...) is not consistently surfacing the right doc's chunks in the top-{K}. "
            f"Check the chunking (chunks too big/unfocused dilute the match) and that similarity "
            f"is computed with the question's own embedding, not something else"
        )

    if answer_fact_rate < ANSWER_FACT_THRESHOLD:
        not_passed(
            f"answer-fact rate = {answer_fact_rate:.3f} ({fact_hits}/{len(qa)}), below required "
            f"{ANSWER_FACT_THRESHOLD} -- hit@{K} passed ({hit_at_k:.3f}), so retrieval is finding the "
            f"right chunks; check that answer(...) actually grounds its response in `retrieved` and "
            f"states the fact plainly rather than paraphrasing it away"
        )

    passed(
        f"hit@{K}={hit_at_k:.3f} ({hits}/{len(qa)}, required >= {HIT_AT_K_THRESHOLD}), "
        f"answer-fact rate={answer_fact_rate:.3f} ({fact_hits}/{len(qa)}, required >= {ANSWER_FACT_THRESHOLD})"
    )


if __name__ == "__main__":
    main()
