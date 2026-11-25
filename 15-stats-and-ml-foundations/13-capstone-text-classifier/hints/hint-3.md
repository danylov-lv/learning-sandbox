**CP1, concretely.** `data.load_titles_and_labels()` gives you parallel
`titles`/`labels` lists; `data.make_split(titles, labels)` gives you
`train_idx`/`test_idx`. Slice both lists by those indices to get
`train_titles`/`train_labels`/`test_titles`/`test_labels`. Construct a
`TfidfVectorizer()`, call `.fit_transform(train_titles)` to get your
training feature matrix AND fit the vectorizer's vocabulary in one call,
then call `.transform(test_titles)` (not `fit_transform` again) to get
matching test features from the SAME vocabulary. Fit a
`LogisticRegression(max_iter=...)` on the training features/labels, call
`.predict(...)` on the test features. Return `(test_labels, predictions)`
in that order — `test_labels` IS your `y_true`, already in the right order
because you sliced by `test_idx` the same way the validator does.

**CP2, concretely.** Tokenize every title the same simple way (e.g.
`title.lower().split()`). Build a vocabulary dict `{token: id}` by counting
token frequencies across TRAINING titles only, keeping (say) the most
frequent few thousand, reserving id 0 for out-of-vocabulary/padding. Write
a small function that maps a title's token list to a fixed-length id
sequence (pad short ones, truncate long ones to some small max length — 4
tokens is typical here, so a small max like 6-8 covers essentially every
title). Encode the string labels to integer class ids with a fixed mapping
(sort the distinct category names once, index into that sorted list — do
this the same way for both encoding and decoding so ids and strings stay
consistent). Batch the training data (plain slicing into fixed-size chunks
is fine, `DataLoader` is also fine), and for each batch: zero the
optimizer's gradients, forward pass through your model to get logits, compute
`nn.CrossEntropyLoss()(logits, integer_labels_batch)`, call `.backward()`,
step the optimizer. Repeat for a handful of epochs over the full training
set. Set `torch.manual_seed(TORCH_SEED)` once before building the model and
starting training. After training, switch to `model.eval()`, wrap inference
in `torch.no_grad()`, run the test set through the model, take `argmax`
over the logits to get predicted class ids, and map those back to category
strings using the same sorted-label mapping you used to encode them.
Return `(test_labels, predicted_category_strings)`.

**Computing macro-F1 yourself, before the validator does.** While
developing, don't wait for `tests/validate_cp1.py` / `validate_cp2.py` to
tell you the number — call `sklearn.metrics.f1_score(y_true, y_pred,
average="macro")` yourself in a scratch script, and also
`f1_score(y_true, y_pred, average=None, labels=sorted(set(y_true)))` to see
the per-class breakdown while you iterate. Put any scratch scripts under a
gitignored `scratch/` directory inside this task, not in the module root.
