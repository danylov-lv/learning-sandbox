No ready-made code -- just the concrete shape of each function.

**`build_index(docs, client)`**: for each doc in `docs`, split `doc["text"]`
on blank lines (`"\n\n"`) into a list of non-empty, stripped paragraphs.
For each paragraph, build a chunk dict carrying at least `doc_id` (from the
parent doc) and `text` (the paragraph itself). Collect every chunk from
every doc into one flat list. Call `client.embed([...])` ONCE with the
full list of chunk texts, in order, and zip the returned vectors back onto
the chunk dicts as an `"embedding"` key. Return the flat list of chunk
dicts -- that's your `index`.

**`retrieve(index, question, client, k)`**: `q_vec =
client.embed([question])[0]`. For each chunk dict in `index`, compute
`harness.llm.cosine(q_vec, chunk["embedding"])`. Sort the chunks by that
score, descending, and return the first `k` chunk dicts (still carrying
their `doc_id` and `text` -- the embedding vector itself doesn't need to
survive into the returned list, but it's harmless if it does).

**`answer(question, retrieved, client)`**: join the retrieved chunks into
one context string, something like `"\n\n".join(f"[{c['doc_id']}]
{c['text']}" for c in retrieved)`. Build a prompt: state the context block,
then the question, then an explicit instruction to answer using only that
context and to say so plainly if the context doesn't cover it. Call
`client.generate(prompt, temperature=0.0)` and use its return value as
`"answer"`. Build `"citations"` from the distinct `doc_id`s already present
in `retrieved` (e.g. `sorted({c["doc_id"] for c in retrieved})`) -- you
already know which docs contributed, no extra lookup needed.
