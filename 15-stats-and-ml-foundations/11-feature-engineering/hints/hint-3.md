Concrete shape of one way to build this (not the only way -- adjust
freely, but this is a working recipe):

- `cat_cols = pandas.get_dummies(df["category"], prefix="cat")` -- a
  DataFrame with one 0/1 column per category value.
- `site_cols = pandas.get_dummies(df["source_site"], prefix="site")` --
  same idea for source_site.
- From `df["scraped_at"]` (a datetime64 Series), pull `.dt.dayofweek`,
  `.dt.month`, `.dt.hour` as numeric Series, and build `is_weekend` as
  `(df["scraped_at"].dt.dayofweek >= 5)`. Either leave day-of-week/month as
  numeric columns or one-hot them the same way as category/site -- both are
  reasonable, one-hot is a bit richer for a linear regressor since it
  doesn't imply "month 12 is twelve times month 1."
- For title, the simple route: `title_len = df["title"].str.len()`,
  `word_count = df["title"].str.split().str.len()`,
  `digit_count = df["title"].str.count(r"\d")` -- all vectorized string
  ops, no Python loop needed. The richer route:
  `from sklearn.feature_extraction.text import TfidfVectorizer;
  vec = TfidfVectorizer(max_features=300); title_matrix =
  vec.fit_transform(df["title"])` -- fit directly on the full `df["title"]`
  column (not just the train rows; `evaluate` handles the
  train/test split itself downstream, and fitting the vectorizer on all
  titles here is a convenience, not a leakage risk, since price never
  enters this function at all).
- Assemble: if everything you built is dense (no vectorizer), stack the
  dense pieces column-wise -- `pd.concat([cat_cols, site_cols, ...],
  axis=1).to_numpy(dtype=float)` or `np.column_stack([...])`. If you added
  a sparse TF-IDF/hashing matrix, wrap your dense stack in
  `scipy.sparse.csr_matrix(...)` first, then
  `scipy.sparse.hstack([dense_sparse, title_matrix]).tocsr()` -- `evaluate`
  accepts a sparse matrix directly (it checks with `scipy.sparse.issparse`
  internally).
- Whatever you return, its row count must equal `len(df)` and its rows
  must be in the same order as `df` -- don't sort, group, or drop rows
  anywhere in this function. `evaluate` indexes your returned matrix with
  positional row indices from `make_split(df)`, computed against this same
  `df`.

Sanity-check before running the validator: call
`engineered_features(df).shape[0]` (or `len(engineered_features(df))` for
a sparse matrix -- use `.shape[0]` there too) and confirm it equals
`len(df)`, not the row count of some filtered subset.
