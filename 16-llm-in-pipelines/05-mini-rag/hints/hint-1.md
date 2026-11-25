Think about what "relevant" means to an embedding model. Two pieces of text
get a high cosine similarity when they're *about the same thing*, even if
they don't share any exact words. That's the whole reason to embed the
question and the document chunks with the same model and compare vectors,
rather than doing a keyword search.

But similarity is computed between whatever two pieces of text you hand the
embedding model. If you embed an entire six-paragraph document as one
vector, you're asking "how similar is this question to this document as a
whole" -- and a document that talks about five different things gets a
diluted, blurry vector that doesn't strongly match any one of them. What
would happen if you broke each document into smaller pieces first, and
compared the question against each piece separately?

Separately: once you have a handful of relevant pieces of text, what's the
most reliable way to get a model to answer using ONLY what's in front of
it, rather than whatever it might already "know" (or guess) about the
topic?
