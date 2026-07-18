# 13 — Capstone: Text Classifier (Title -> Category)

## Backstory

The scraper landed a catalog with titles but the category field is missing
or garbage on a meaningful fraction of rows — a familiar mess: the source
site's own taxonomy is inconsistent, category came from a field that
sometimes just isn't populated, or a normalization step upstream dropped it.
Nobody is going to hand-label 60000 rows. What you do have is the title
string on every row, and titles carry real (if imperfect) category signal —
"Northlane Rustic tablet N896" is obviously electronics-shaped even without
a category field to confirm it.

This capstone is the module's Arc C payoff: build a classifier that
recovers `category` from `title` alone, first the boring-but-strong way
(a linear model over bag-of-words features), then the neural way (a small
PyTorch model you train yourself), then write up what you built and why it
works well enough — and where it doesn't.

## What's given

- `src/data.py` — a fully-implemented (not a stub) shared fixture:
  `SPLIT_SEED = 42`, `TEST_SIZE = 0.2`, `load_titles_and_labels()` (loads
  `title`/`category` for every row via `harness.common.load_observations()`),
  and `make_split(titles, labels)` (a deterministic, stratified 80/20
  train/test split by index, via
  `sklearn.model_selection.train_test_split(random_state=SPLIT_SEED,
  stratify=labels)`). Every checkpoint's `run()`, and every validator, must
  use this exact split — it's what lets CP1, CP2, and their validators all
  grade against the same held-out rows.
- `src/baseline.py`, `src/model.py`, `src/train.py` — stubs, one function or
  class body per checkpoint, `raise NotImplementedError` with a docstring
  spelling out the contract.
- `DESIGN.md` — an unfilled template with six sections for CP3.
- Three checkpoint validators: `tests/validate_cp1.py`, `validate_cp2.py`,
  `validate_cp3.py`.

## What's required

### CP1 — classical baseline (`validate_cp1.py`)

**Build:** in `src/baseline.py`, implement `run() -> (y_true, y_pred)`. Use
`src/data.py` to load titles/labels and get the shared split. Vectorize the
TRAINING titles only (`TfidfVectorizer` or `CountVectorizer`), fit a linear
classifier (`LogisticRegression` or `LinearSVC`) on the vectorized train
set, and predict on the vectorized test titles using the same fitted
vectorizer.

**Checked:** macro-F1 (`sklearn.metrics.f1_score(average="macro")`) over
the held-out split is at or above a threshold set well below what a solid
TF-IDF + linear-classifier baseline reaches on this dataset — headroom for
a reasonable, not perfectly-tuned, implementation. Also checked: `y_true`
matches the labels of the rows `src/data.py`'s `make_split` actually holds
out, proving `run()` used the shared split and not something else.

### CP2 — PyTorch classifier (`validate_cp2.py`)

**Build:** in `src/model.py`, a small `nn.Module` (`TitleClassifier`) —
something like: map tokens to ids, embed, pool across a title's tokens into
one fixed-size vector, then a linear layer over that vector produces one
logit per category. In `src/train.py`, implement `run() -> (y_true, y_pred)`
that tokenizes titles, builds a vocabulary from the TRAINING split only,
trains `TitleClassifier` with cross-entropy on CPU with fixed seeds, and
predicts on the same held-out test split CP1 was graded against.

**Checked:** the same shape of check as CP1 — macro-F1 at or above a
threshold, `y_true` matching the shared split's held-out labels. Keep the
vocabulary and epoch count small; this checkpoint should train in well
under two minutes on CPU. `validate_cp2.py` reports the wall-clock runtime
(no pass/fail on it, but a multi-minute run is a sign to shrink something).

### CP3 — design memo + regression gate (`validate_cp3.py`)

**Build:** fill in every section of `DESIGN.md` — data and labels, text
representation/tokenization, model architecture, training and evaluation,
per-class error analysis, and scaling to real catalogs.

**Checked:** `DESIGN.md` is gated first (every required section present,
filled with real content past the shipped placeholder, a minimum length
per section, and a handful of grounding keywords proving the memo is about
THIS capstone — macro-F1, tf-idf/embedding, tokenization, class imbalance —
not generic prose). Only once that passes does the validator re-run CP1 and
CP2 as subprocesses (`uv run python tests/validate_cp1.py` /
`validate_cp2.py`) and require both to still print `PASSED`. A design memo
for a classifier that no longer meets its own thresholds doesn't pass this
one either.

## Completion criteria

Once, from the module root:

```bash
uv run python generate.py
```

Then, from this task's directory:

```bash
uv run python tests/validate_cp1.py
uv run python tests/validate_cp2.py
uv run python tests/validate_cp3.py
```

The task is complete when all three print `PASSED` and exit 0. Any
failure — a stub still raising `NotImplementedError`, a macro-F1 below
threshold, `y_true` not matching the shared split, or an unfilled
`DESIGN.md` — prints a single `NOT PASSED: <reason>` line and exits 1.

## Estimated evenings

2-4

## Topics to read up on

- Text vectorization: bag-of-words, TF-IDF weighting, and the hashing trick
- Tokenization (why a simple whitespace split is enough for short,
  templated titles, and where it would stop being enough)
- Class imbalance and why macro-F1 (unweighted per-class average) tells a
  different story than accuracy or micro-F1 on an imbalanced label set
- `torch.nn.Module`, embeddings (`nn.Embedding` / `nn.EmbeddingBag`), and
  pooling a variable-length sequence into a fixed-size vector
- Cross-entropy loss and why raw logits (not softmax output) are what
  `nn.CrossEntropyLoss` expects
- Train/validation discipline: fitting a vectorizer or building a
  vocabulary on training data only, never on held-out data
- Stratified train/test splits, and why they matter more as class balance
  gets more skewed
- Per-class error analysis: which categories a model confuses, and why

## Off-limits

`.authoring/design.md` (at the module root) holds the harness API contract,
the dataset schema, and the measured baseline macro-F1 this task's
thresholds are calibrated against — spoilers. Don't read it before
finishing this task. `DESIGN.md` in this task directory is yours to fill in
for CP3 — it ships as an empty template, not something to read for hints.
