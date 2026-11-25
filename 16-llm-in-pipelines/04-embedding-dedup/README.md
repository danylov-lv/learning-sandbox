# 04 -- Embedding Dedup

## Backstory

Three different scrapers feed the same catalog, and none of them agree on
how to write a product title. One writes `Voltix Compact earbuds A123`.
Another abbreviates: `Voltix Cpt earbuds A123`. A third reorders and adds
punctuation: `Compact earbuds A123 (Voltix)`. A fourth writes `Voltix,
Compact earbuds - A123`. All four rows are the same physical product, and
right now the catalog lists it four times.

An exact string match catches none of these. A fuzzy string match (edit
distance, token-set overlap) catches some of the easy ones but chokes on
"Compact" vs "Cpt" -- that's a meaning-preserving abbreviation, not a
small character edit, and no string-distance metric knows the difference.
Meanwhile two rows that share a brand and an adjective but describe
genuinely different products (different noun, different model number)
need to stay apart, not get merged just because they overlap on tokens.

This is exactly the kind of problem a local embedding model is good at:
map every title to a vector that captures what it MEANS, not how it's
spelled, and duplicates land close together in that vector space
regardless of surface form.

## What's given

- `data/dedup.json` (gitignored, built by `uv run python generate.py` at
  the module root) -- a list of `{item_id, title}` objects. ~55 items,
  title variants of ~20 distinct underlying products, list order shuffled
  so duplicates are never adjacent.
- `harness/llm.py` -- `get_client()` (returns a ready `LLMClient`),
  `client.embed(texts: list[str]) -> list[list[float]]` (batched
  embedding via the local `nomic-embed-text` model), and `cosine(a, b)`
  (cosine similarity between two vectors).
- `harness/common.py` -- `require_client()` (checks Ollama is up and both
  models are pulled before trusting any output) and `pair_f1(pred_labels,
  gold_labels)` (pairwise clustering-agreement F1, used by the validator).
- `src/dedup.py` -- the scaffold you implement. One function,
  `cluster_items(items, client)`, with a docstring that spells out the
  exact input/output contract and a suggested (not mandatory) approach.

## What's required

Implement `cluster_items(items, client)` in `src/dedup.py`. It must embed
each item's title using `client.embed`, compare titles by similarity in
that embedding space, and return a dict mapping every `item_id` to a
cluster label such that items describing the same underlying product get
the same label and items describing different products get different
labels. The label values themselves don't matter -- only which item_ids
end up grouped together.

You choose the clustering mechanism: a similarity threshold plus
connected components (union-find) is the simplest approach and is
entirely sufficient here, but an off-the-shelf method like
`sklearn.cluster.AgglomerativeClustering` over a cosine-distance matrix
works too if you'd rather not hand-roll the graph traversal.

## Completion criteria

From the module root:

```bash
uv run python 04-embedding-dedup/tests/validate.py
```

The validator loads `data/dedup.json`, calls `cluster_items`, and
compares the resulting partition against an independently-reconstructed
gold partition using pairwise clustering F1 (`pair_f1` in
`harness/common.py`): for every pair of items, does your clustering agree
with gold on whether they're the same product. It must clear a threshold
set well below what a reasonable similarity-threshold-based clustering
achieves on this data, and well above what either degenerate shortcut
(everything its own cluster, or everything one cluster) achieves.

Prints `PASSED` with the measured precision/recall/F1, or `NOT PASSED:
<reason>` and exits 1 -- including while `src/dedup.py` is still
unimplemented (`NotImplementedError` surfaces as a clean message, no
traceback). Requires the module's Ollama container to be running with
both `qwen2.5:7b-instruct` and `nomic-embed-text` pulled (`require_client`
checks this first and tells you exactly what to run if it isn't).

## Estimated evenings

1-2

## Topics to read up on

- Text embeddings -- what a vector embedding captures that a raw string
  comparison doesn't
- Cosine similarity as a distance metric between embedding vectors
- Connected components / union-find, as a way to turn a pairwise
  similarity threshold into a partition
- Agglomerative (hierarchical) clustering, as an alternative to
  threshold-based connected components
- Pairwise clustering evaluation (precision/recall/F1 over item pairs) --
  why it's a more informative metric than raw cluster-count agreement
  when the number of true clusters isn't known in advance

## Off-limits

`.authoring/design.md` (at the module root) holds the harness API
contract, the exact dataset generation process, and this task's
verification margins -- spoilers. Don't read it before finishing this
task.
