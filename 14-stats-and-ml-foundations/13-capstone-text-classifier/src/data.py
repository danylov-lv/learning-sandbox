"""Shared split fixture for the text-classification capstone (t13).

This file is GIVEN, fully implemented -- not a stub. Every checkpoint (CP1's
classical baseline, CP2's torch model) and every validator must grade
predictions on the exact SAME held-out rows, so the train/test split is
fixed here once, with a fixed seed, and imported everywhere else. Do not
re-split with a different seed or a different function anywhere else in this
task -- that would silently disagree with what the validators expect.

The data itself is the module's shared scraped-catalog dataset
(`harness.common.load_observations()`): titles carry real but imperfect
category signal (see `.authoring/design.md` for how -- off-limits until
you've finished this task), so a classifier trained on titles alone can do
well, but not trivially perfectly.
"""

from sklearn.model_selection import train_test_split

import sys
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parents[2]
if str(MODULE_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE_ROOT))

from harness.common import load_observations  # noqa: E402

# Fixed split contract -- shared by every checkpoint and every validator.
# Do not change these values; changing them changes which rows are held out
# and silently invalidates every threshold tuned against this split.
SPLIT_SEED = 42
TEST_SIZE = 0.2


def load_titles_and_labels():
    """Load the full shared dataset as parallel lists of titles and labels.

    Returns:
        (titles, labels): two lists of str, same length (one entry per
        observation in the shared dataset), in the row order
        `load_observations()` returns them (no shuffling here -- shuffling,
        if any, happens inside `make_split` via `train_test_split`).
        `titles[i]` is that row's `title` string; `labels[i]` is that row's
        `category` string (one of the 8 categories in the shared dataset).
    """
    df = load_observations()
    return df["title"].tolist(), df["category"].tolist()


def make_split(titles, labels):
    """Deterministic, stratified 80/20 train/test split, by index.

    Splits POSITIONAL INDICES into `titles`/`labels` (not the strings
    themselves) via `sklearn.model_selection.train_test_split` with
    `random_state=SPLIT_SEED`, `test_size=TEST_SIZE`, and
    `stratify=labels` (so the class balance in each split mirrors the full
    dataset -- important here since categories are far from balanced, see
    the per-category counts in `harness.common.load_observations()`).

    Every checkpoint's `run()` must call this function (via
    `load_titles_and_labels` + `make_split`) rather than constructing its
    own split -- the validators independently recompute the same
    `test_idx` and check that the labels a checkpoint's `run()` reports as
    `y_true` match those held-out rows exactly, in order. A different seed,
    a different `test_size`, or a non-stratified split will all produce a
    `test_idx` that does not match and will fail that check.

    Args:
        titles: list[str], as returned by `load_titles_and_labels()`.
        labels: list[str], same length and row order as `titles`.

    Returns:
        (train_idx, test_idx): two lists of int, positional indices into
        `titles`/`labels` (0-based, disjoint, together covering every
        index exactly once). `len(test_idx) / len(titles) ~= TEST_SIZE`.
    """
    n = len(titles)
    indices = list(range(n))
    train_idx, test_idx = train_test_split(
        indices,
        test_size=TEST_SIZE,
        random_state=SPLIT_SEED,
        stratify=labels,
    )
    return train_idx, test_idx
