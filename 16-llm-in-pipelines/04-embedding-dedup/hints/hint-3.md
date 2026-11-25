No ready-made code here -- just the concrete shape.

1. `titles = [it["title"] for it in items]`, then one batched call:
   `vecs = client.embed(titles)`.
2. Normalize every vector to unit length and compute the full pairwise
   cosine-similarity matrix in one shot (`normed = vecs / norms`, then
   `sim = normed @ normed.T`) rather than calling `cosine()` inside a
   double loop -- both work, the matrix version is just faster for ~55
   items and scales better if you reuse this on a bigger set later.
3. Try a range of thresholds by eye first (print how many pairs exceed
   0.95, 0.90, 0.85, 0.80, ...) to get a feel for where genuine duplicates
   separate from genuine non-duplicates in this embedding space, before
   locking one in.
4. Build a union-find (a `parent` array of `len(items)`, `find` with path
   compression, `union` on any pair whose similarity clears your chosen
   threshold), run it over every pair once, then call `find(i)` for every
   item to get its cluster root -- that root value (or any label you
   derive from it, e.g. `str(root)`) is the label you return.
5. Return `{items[i]["item_id"]: label_for(find(i)) for i in
   range(len(items))}`.

If you'd rather not hand-roll union-find, `sklearn.cluster
.AgglomerativeClustering(n_clusters=None, distance_threshold=..., metric=
"cosine", linkage="average")` fit on the raw vectors does the same job --
remember `distance_threshold` is a DISTANCE (1 - cosine_similarity), not
a similarity, so invert whatever similarity threshold you settled on
above.
