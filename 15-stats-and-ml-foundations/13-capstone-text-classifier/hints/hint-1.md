Titles carry a lot more category signal than they might look like at first
glance — brand tokens and noun tokens are both strongly associated with
particular categories, even though the dataset was built to dilute that
signal somewhat rather than make it trivial. Before reaching for anything
neural, get a bag-of-words-style linear model working end to end (CP1). It
is not a throwaway baseline to be immediately discarded once CP2's PyTorch
model shows up — on short, templated titles like these, a well-tuned linear
model over the right features is a genuinely strong result, and CP2's model
should be judged against it, not against some abstract idea of "neural
models are always better."

Get the full pipeline working — load data, split, vectorize, fit, predict,
score — before worrying about which vectorizer or classifier variant gives
the best number. A correct, simple pipeline beats a half-finished
sophisticated one.
