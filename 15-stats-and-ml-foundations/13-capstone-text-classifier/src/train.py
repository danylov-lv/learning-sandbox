"""t13 CP2 -- tokenization, vocabulary, training loop, and evaluation for
the torch title classifier.

This is where `src/model.py`'s `TitleClassifier` gets wired up into
something trainable: turning titles into token-id sequences, building a
vocabulary, training with cross-entropy on the SAME held-out split CP1
graded against, and reporting predictions on that same held-out set.

No solution is provided anywhere in this task -- work it out from this
docstring, the README, and the hints. Use `src/data.py`'s
`load_titles_and_labels` / `make_split` for the data and split; do not
construct your own split.
"""

from src import data
from src.model import TitleClassifier  # noqa: F401  (import for learners to wire up)

# Fix every source of randomness your training loop touches (torch's global
# RNG at minimum -- `torch.manual_seed(TORCH_SEED)`; also numpy/`random` if
# you use them for shuffling or negative sampling) so runs are reproducible
# and the reported macro-F1 doesn't wander between runs on the same machine.
TORCH_SEED = 1234


def run():
    """Train `TitleClassifier` and evaluate it on the held-out split.

    Build, roughly:
      1. `titles, labels = data.load_titles_and_labels()`
      2. `train_idx, test_idx = data.make_split(titles, labels)`
      3. Tokenize titles (e.g. lowercase + split on whitespace -- titles
         are template-generated as "<brand> <adjective> <noun> <model>", so
         a simple whitespace split already gives you 4 clean tokens per
         title; no need for a heavier tokenizer).
      4. Build a token -> id vocabulary from the TRAIN titles only (fitting
         it on test titles too is the same leakage bug as CP1's
         vectorizer -- the model shouldn't get to "see" test-set tokens
         while building its vocabulary). Reserve an id for
         out-of-vocabulary tokens encountered at eval time (a test title
         may contain a token never seen in train) and, if you pad
         sequences to a common length, a separate id for padding. Keep the
         vocabulary small -- capping it to the most frequent N tokens (or
         hashing tokens into a fixed number of buckets) keeps the embedding
         table small and training fast; you do not need one id per unique
         token if the long tail is rare.
      5. Encode labels as integer class ids (e.g.
         `sklearn.preprocessing.LabelEncoder`, or your own fixed mapping
         over the 8 known categories) -- `nn.CrossEntropyLoss` wants
         integer class targets, not strings.
      6. Build a training loop: batch the train titles (a plain manual
         batching loop is fine; `torch.utils.data.DataLoader` is also
         fine), forward pass through `TitleClassifier`, `nn.CrossEntropyLoss`
         against the integer labels, backward pass, optimizer step (e.g.
         `torch.optim.Adam`). A handful of epochs over ~48000 training
         titles with a small vocab/embedding is enough to get well above
         chance on CPU in well under the module's runtime budget -- resist
         the urge to over-train; watch the smaller classes in particular
         (macro-F1 weights every class equally regardless of how many rows
         it has, so a model that only nails the two largest categories
         will score worse on this metric than the per-class accuracy
         numbers might suggest).
      7. Run the trained model over the encoded TEST titles (`model.eval()`,
         `torch.no_grad()`), decode predicted class ids back to category
         strings.

    Returns:
        (y_true, y_pred): two lists of str category labels, same length,
        aligned by position.
          - `y_true` must be exactly `[labels[i] for i in test_idx]` from
            `data.make_split` -- the validator independently recomputes
            `test_idx` and checks this matches exactly.
          - `y_pred` must be your model's predicted category (decoded back
            to the original string labels, not integer class ids) for each
            of those same held-out titles, in the same order as `y_true`.
    """
    raise NotImplementedError
