**`extract_record`, concretely.** Build a prompt that lists the 5 fields
and their expected types explicitly (this is the same lesson as t02 --
name the edge cases: integer-cents prices, attribute-only fields,
prose-only price, no dedicated stock boolean). Call
`client.generate(prompt, format="json", temperature=0.0)`. Then:

```
try:
    data = json.loads(response_text)
except (json.JSONDecodeError, TypeError):
    return {"name": None, "brand": None, "price": None, "currency": None,
            "in_stock": None, "confidence": 0.0, "valid": False}

fields = {"name": ..., "brand": ..., "price": ..., "currency": ..., "in_stock": ...}
# validate each: non-empty str for name/brand, float()-able for price,
# 3-letter code for currency, actual bool for in_stock -- fields.get(k)
# that don't validate become None
present = sum(1 for v in fields.values() if v is not None)
confidence = present / len(fields)
return {**fields, "confidence": confidence, "valid": confidence >= YOUR_THRESHOLD}
```

`classify_record` follows the same shape, but the validity check is
simpler: `category in generate.CATEGORIES` and `brand` non-empty, each
worth half the confidence (or just `1.0`/`0.0` -- either is defensible,
CP1/CP2 grade the routing OUTCOME, not your exact formula).

**`dedup_cluster`, concretely.**

```
titles = [it["title"] for it in items]
try:
    vectors = client.embed(titles)
except Exception:
    return [{"item_id": it["item_id"], "cluster_id": it["item_id"],
              "confidence": 0.0, "valid": False} for it in items]

assigned = [-1] * len(items)
next_cluster = 0
results = [None] * len(items)
for i in range(len(items)):
    if assigned[i] != -1:
        continue
    assigned[i] = next_cluster
    for j in range(i + 1, len(items)):
        if assigned[j] == -1 and cosine(vectors[i], vectors[j]) >= SIM_THRESHOLD:
            assigned[j] = next_cluster
    next_cluster += 1

for i, it in enumerate(items):
    results[i] = {"item_id": it["item_id"], "cluster_id": assigned[i],
                   "confidence": 1.0, "valid": True}
return results
```

Tune `SIM_THRESHOLD` empirically -- print the pairwise cosine similarities
for a few known-same-cluster and known-different-cluster title pairs from
`data/dedup.json` (or your own scratch script) while you calibrate it.

**`run_pipeline`'s routing loop, concretely.**

```
catalog, quarantine = [], []
for stage_name, results, id_key in (
    ("extraction", extraction_results, "snippet_id"),
    ("classification", classification_results, "record_id"),
    ("dedup", dedup_results, "item_id"),
):
    for r in results:
        tagged = {**r, "stage": stage_name, "id": r[id_key]}
        if r["valid"]:
            catalog.append(tagged)
        else:
            quarantine.append({**tagged, "reason": "low confidence"})
```

**`explain_product`, concretely.** Render every candidate with
`render_catalog_doc`, `client.embed(docs + [question])` in one call (the
question is just the last element), compute cosine similarity between the
question's vector and every doc's vector, take the top 2-3 `product_id`s,
build a short context block (`"\n".join(top_docs)`), and prompt
`client.generate(f"Context:\n{context}\n\nQuestion: {question}\nAnswer using
only the context above, and name which product(s) you used.")`. Parse the
product_id(s) you used from the top-k you retrieved (you already know
which docs you fed in -- you don't need to re-parse them out of the model's
free-text answer) and return them as `citations`.
