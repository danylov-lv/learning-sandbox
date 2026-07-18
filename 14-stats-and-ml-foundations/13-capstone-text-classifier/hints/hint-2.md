For CP2's torch model, the pipeline has a fixed shape regardless of the
exact architectural choices you make: map each title's tokens to integer
ids using a vocabulary built from training data, look up an embedding
vector per token id, pool the per-token embeddings into one fixed-size
vector per title (mean pooling is simplest and works fine here — titles are
short and word order carries little signal), then a linear layer over that
pooled vector produces one logit per category. Train with
`nn.CrossEntropyLoss` against integer class ids, not the string labels
directly, and don't apply softmax yourself before the loss — the loss
function does that internally.

Watch the smaller categories specifically once you have a trained model.
Macro-F1 (what both checkpoints are graded on) weights every class equally
regardless of how many rows it has — a model that nails the two largest
categories but does poorly on the smallest ones will score noticeably
worse on macro-F1 than its overall accuracy would suggest. If your macro-F1
is surprisingly low despite a model that "looks" like it's training fine,
break down performance per class before assuming something is broken in
your training loop.

Keep the vocabulary and the embedding dimension small, and don't over-train
— a handful of epochs over the training split is enough to get well past
this checkpoint's threshold. This is meant to run in well under two minutes
on CPU.
