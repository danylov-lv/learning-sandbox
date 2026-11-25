"""t13 CP1 -- classical baseline: predict product category from title text.

Your scraped catalog has titles but the category labels are missing or
garbage for a meaningful fraction of live rows (a familiar problem: a site's
own category taxonomy is inconsistent, or the field never got scraped
cleanly). Before reaching for anything fancy, build the boring, strong
baseline: a bag-of-words-style vectorizer feeding a linear classifier. This
kind of model is fast to train, fast to run, and -- on short, templated
product titles like these -- a genuinely hard baseline to beat, not a straw
man to be immediately discarded once CP2's neural model shows up.

No solution is provided anywhere in this task -- work it out from this
docstring, the README, and the hints. Use `src/data.py`'s
`load_titles_and_labels` / `make_split` for the data and split; do not
construct your own split.
"""

from src import data


def run():
    """Fit a classical text classifier and evaluate it on the held-out split.

    Build, roughly:
      1. `titles, labels = data.load_titles_and_labels()`
      2. `train_idx, test_idx = data.make_split(titles, labels)`
      3. Vectorize the TRAIN titles only (e.g.
         `sklearn.feature_extraction.text.TfidfVectorizer` or
         `CountVectorizer`) -- fit the vectorizer on train titles, then use
         the SAME fitted vectorizer to transform the test titles. Fitting
         (or re-fitting) the vectorizer on test titles is a leakage bug:
         the vectorizer's vocabulary would then have "seen" the test set.
      4. Train a linear classifier (e.g. `LogisticRegression` or
         `LinearSVC`) on the vectorized train titles and their labels.
      5. Predict categories for the vectorized test titles.

    Returns:
        (y_true, y_pred): two lists (or 1-D array-likes) of str category
        labels, same length, aligned by position.
          - `y_true` must be exactly `[labels[i] for i in test_idx]` --
            i.e. the true labels of the held-out rows from `data.make_split`,
            in `test_idx` order. The validator independently recomputes
            `test_idx` and checks this matches exactly; a different split
            (different seed, shuffled differently, or a subset) will fail
            this check even if your model's predictions are otherwise fine.
          - `y_pred` must be your model's predicted category for each of
            those same held-out titles, in the same order as `y_true`.
    """
    raise NotImplementedError
