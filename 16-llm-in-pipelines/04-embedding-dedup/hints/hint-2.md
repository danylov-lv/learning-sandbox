`client.embed(texts)` gives you one vector per title, in the same order as
the input list -- call it once with all titles rather than once per item,
it's the same number of network calls either way but keeps your code
simpler. From there, `harness.llm.cosine(a, b)` gives you similarity
between any two vectors, or you can normalize the whole vector matrix and
take a single matrix product to get every pairwise similarity at once
(much faster than looping over all n^2 pairs one at a time for pure
cosine calls).

The real design decision is what to do with a similarity number. A fixed
threshold turns "compare two vectors" into a yes/no "are these the same
product" call. Once you have yes/no edges between items, you have a
graph, and "which items belong together" is just "which items are
connected" -- a classic connected-components problem, solvable with
union-find in a few lines, or you can hand the similarity/distance matrix
to a library clustering method instead if you'd rather not write the
graph traversal yourself.

Watch out for the transitive-closure trap either way: if A-B are similar
and B-C are similar but A-C are not (a three-item cluster where the
"outer" two variants drifted furthest from each other), a naive pairwise
threshold still correctly merges all three into one cluster through B --
that's a feature of connected components, not a bug, but it means your
threshold needs to be loose enough to catch every true duplicate pair
somewhere in the chain, not so loose it starts merging different
products.
