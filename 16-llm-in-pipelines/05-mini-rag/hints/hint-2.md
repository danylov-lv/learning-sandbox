Chunking: split each doc's text into smaller pieces before embedding --
paragraphs (split on blank lines) is a natural unit for short markdown docs
like these, since each paragraph tends to stay on one topic. Whatever
splitting scheme you use, carry the doc's `doc_id` along with every chunk
you produce from it, in whatever structure you return from `build_index`
-- a list of dicts (`{"doc_id": ..., "text": ..., "embedding": ...}`) is
the simplest shape and works fine as the `index` object `retrieve` later
consumes.

Embedding: `client.embed(texts)` takes a *list* of strings and returns one
vector per string, in the same order -- call it once with all your chunk
texts in `build_index`, not once per chunk in a loop, and not again inside
`retrieve` for anything except the question itself (embedding chunks
should happen exactly once, up front).

Retrieval: embed the question with `client.embed([question])[0]` (note the
list wrapping and the `[0]` unwrap -- `embed` always takes and returns a
list, even for one item). Then score every chunk against that one question
vector with `harness.llm.cosine(question_vec, chunk_vec)`, sort
descending, and slice the top `k`.

Answering: build a prompt that includes the retrieved chunks' text as
literal context (label each chunk with its `doc_id` so the model can refer
back to it), and instruct the model explicitly to answer only from that
context. Read the retrieved list you were passed for the doc_ids to put in
`citations` -- don't invent them and don't call `retrieve` again inside
`answer`.
