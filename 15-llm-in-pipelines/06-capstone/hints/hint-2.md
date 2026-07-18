**Confidence and validity.** You don't need a sophisticated confidence
model. A simple, defensible approach: after asking the model for JSON and
parsing the response, count how many of the required fields came back
non-empty and of the right type. `confidence = that count / total required
fields`. Wrap the whole "call the model, parse the response" sequence in a
`try/except` — on ANY exception (JSON decode error, `KeyError`,
`TypeError`, whatever), catch it and return a record with `confidence=0.0`,
`valid=False`, and every field you couldn't recover set to `None`, rather
than letting the exception escape the function. `valid` itself is just
`confidence >= <a threshold you pick and can justify>` — you don't have to
get this threshold "right" on the first try; CP1 tells you if it's
rejecting too many good records (quarantine rate too high on clean input),
and CP2 tells you if it's letting too many bad ones through (catalog
precision too low under chaos).

**`run_pipeline`'s shape.** Call `extract_record` once per item in
`extraction_items`, in order, tag each result with its `snippet_id`.
Same pattern for `classify_record` over `classification_items`. Call
`dedup_cluster` ONCE with the whole `dedup_items` list (it's a batch
operation, not a per-item one) and it already returns `item_id`-tagged
results. Then walk all three result lists once: any record with
`valid=True` goes into `catalog` (plus a `"stage"` and `"id"` tag); any
record with `valid=False` goes into `quarantine` (same tags, plus a short
`"reason"` string you can derive from which fields came back `None` or
whether the model's JSON parse failed).

**`dedup_cluster`'s clustering.** Embed every title with one
`client.embed(titles)` call (it's already batched — one call, not a loop of
single-item calls). Then a simple greedy approach works fine: walk items in
order, and for each unclustered item, start a new cluster containing it
plus every OTHER unclustered item whose embedding has cosine similarity
(`harness.llm.cosine`) above some threshold. You don't need anything fancier
than that for ~20 well-separated clusters.

**`explain_product`.** `render_catalog_doc` just needs to produce a string
containing every field a plausible question might ask about — don't
overthink the format, a few `key: value` lines or a short sentence per
field both work. In `explain_product`, embed all the candidate docs plus
the question, rank by cosine similarity, and pass only the top 2-3 as
context in your generation prompt, instructing the model to answer ONLY
from that context and to name which product(s) it used.
