"""CP1 validator for t13 -- classical baseline.

Calls `src.baseline.run()`, which must fit a classical text classifier
(TF-IDF/CountVectorizer + a linear classifier) on the training split and
predict on the held-out test split defined by `src/data.py`'s
`SPLIT_SEED`/`TEST_SIZE`. Checks, in order:

  1. `run()` returns a `(y_true, y_pred)` pair of matching length.
  2. `y_true` matches the labels of the held-out rows this validator
     independently recomputes via `data.make_split` -- proof `run()`
     actually used the shared split fixture, not some other split.
  3. macro-F1 (`sklearn.metrics.f1_score(average="macro")`) over
     `(y_true, y_pred)` is >= `CP1_MIN_F1`.

`CP1_MIN_F1` is set well below the ~0.90 macro-F1 a TF-IDF + LogisticRegression
baseline reaches on this dataset (see `.authoring/design.md`, off-limits
until you've finished this task) -- headroom for a reasonable, not
necessarily perfectly-tuned, implementation.

Run from this task's directory:

    uv run python tests/validate_cp1.py
"""

import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))
sys.path.insert(0, str(TASK_ROOT))

from harness.common import guarded, not_passed, passed  # noqa: E402
from src import data  # noqa: E402
from src.baseline import run  # noqa: E402

CP1_MIN_F1 = 0.78


def _per_class_report(y_true, y_pred):
    from sklearn.metrics import f1_score

    labels = sorted(set(y_true))
    scores = f1_score(y_true, y_pred, labels=labels, average=None, zero_division=0)
    return ", ".join(f"{lab}={s:.3f}" for lab, s in zip(labels, scores))


@guarded
def main():
    from sklearn.metrics import f1_score

    titles, labels = data.load_titles_and_labels()
    _, test_idx = data.make_split(titles, labels)
    expected_y_true = [labels[i] for i in test_idx]

    result = run()
    if not isinstance(result, tuple) or len(result) != 2:
        not_passed(f"run() must return a (y_true, y_pred) tuple, got {type(result).__name__}")
    y_true, y_pred = result

    y_true = list(y_true)
    y_pred = list(y_pred)

    if len(y_true) != len(expected_y_true):
        not_passed(
            f"y_true has {len(y_true)} entries, expected {len(expected_y_true)} "
            "(the held-out test split from src/data.py's SPLIT_SEED/TEST_SIZE) -- "
            "did run() call data.make_split()?"
        )
    if len(y_pred) != len(y_true):
        not_passed(f"y_pred has {len(y_pred)} entries, expected {len(y_true)} to match y_true")

    if [str(v) for v in y_true] != [str(v) for v in expected_y_true]:
        not_passed(
            "y_true does not match the held-out labels expected from src/data.py's "
            "make_split(titles, labels) -- run() must evaluate on THIS shared split, "
            "not a different one (check SPLIT_SEED/TEST_SIZE weren't changed, and that "
            "the split was computed on the full dataset before slicing)"
        )

    macro_f1 = f1_score(y_true, y_pred, average="macro", zero_division=0)
    if macro_f1 < CP1_MIN_F1:
        not_passed(
            f"macro-F1={macro_f1:.4f} on the held-out split, expected >= {CP1_MIN_F1} "
            f"-- per-class F1: {_per_class_report(y_true, y_pred)}"
        )

    passed(f"macro-F1={macro_f1:.4f} (>= {CP1_MIN_F1}); per-class: {_per_class_report(y_true, y_pred)}")


if __name__ == "__main__":
    main()
