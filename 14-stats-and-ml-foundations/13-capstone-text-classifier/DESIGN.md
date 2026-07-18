# Capstone Design Memo — Title -> Category Text Classifier

Fill in each section with your own analysis, grounded in what you actually
built and measured across CP1 (`src/baseline.py`) and CP2 (`src/model.py` +
`src/train.py`) of this capstone. Cite real numbers your own runs produced
(macro-F1, per-class F1, runtime) — not numbers you expect or numbers from
this template.

## Data and labels

[fill in — what is `category`, how many distinct classes are there, and how
imbalanced is the label distribution across them (cite the actual per-class
counts from the shared dataset)? What does the fixed train/test split in
`src/data.py` guarantee, and why does every checkpoint (and its validator)
depend on using that exact split rather than each computing its own?]

## Text representation / tokenization

[fill in — how does CP1 turn a title string into features (vectorizer
choice, vocabulary size, any preprocessing), and how does CP2 turn a title
into token ids (tokenization scheme, vocabulary source, how out-of-
vocabulary tokens at test time are handled)? Where was each vocabulary
fit — training data only, or did it see test data too, and why does that
distinction matter?]

## Model architecture

[fill in — describe `TitleClassifier`'s actual shape: embedding dimension,
pooling strategy, any hidden layers, output size. Why is this architecture
a reasonable fit for titles shaped like "<brand> <adjective> <noun>
<model>" specifically — what would a more complex architecture (e.g. one
that used token order) buy you here, if anything?]

## Training and evaluation

[fill in — how was CP2 trained (optimizer, loss, batch size, epoch count,
seeds fixed where), and how long did it take on your machine (cite the
runtime `validate_cp2.py` reported)? Report your own CP1 and CP2 macro-F1
on the held-out split, and say which one scored higher and by how much —
does that match what you expected going in?]

## Per-class error analysis

[fill in — which categories does your model do best/worst on, and why (cite
per-class F1 from your own validator runs)? Is there a pattern to the
errors — e.g. a smaller class getting confused for a larger, related one?
What about the dataset's title construction would make certain categories
inherently harder to separate from titles alone?]

## Scaling to real catalogs

[fill in — this dataset has 8 fixed categories and ~60000 rows. What would
change about your approach (vectorizer/vocabulary size, model capacity,
training time) if the real catalog had 200 categories and 50 million
titles? What would you want to monitor in production if this classifier
were used to backfill missing category labels on live scraped data?]
