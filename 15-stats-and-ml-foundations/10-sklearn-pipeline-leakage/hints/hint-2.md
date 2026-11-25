Target encoding (replacing a category/id with the mean of the target for
that category/id) is a completely legitimate technique -- it's not the
mean that's wrong, it's WHICH rows go into the mean.

Compute a group's mean using every row that belongs to that group,
regardless of split, and a test row's own target is baked into its own
feature -- diluted by however many other rows share that group, but never
removed. For a product with 1 observation, the "average" IS that
observation. For a product with 2, it's half that observation plus half
another. The smaller the group, the closer the leak gets to just handing
the model the answer.

Compute the group's mean using ONLY the train rows, and a held-out test
row's feature value was determined entirely by data the model was
"allowed" to see during fitting -- exactly the same guarantee a
`StandardScaler` gives you when you `.fit()` it on train data and only
`.transform()` the test data with those already-fitted statistics. This is
precisely why `sklearn.pipeline.Pipeline` exists as more than a
convenience: when you call `.fit()` on a Pipeline, every preprocessing
step inside it fits ONLY on the data you hand it. The discipline you need
here -- "compute this statistic from train rows only, then apply it
everywhere" -- is the same discipline a Pipeline enforces automatically
for things like scaling and one-hot encoding. A manually-computed target
encoding sits outside that automatic protection, which is exactly why it's
such an easy place to accidentally leak: nothing stops you from computing
it on the wrong rows unless you're deliberate about the order of
operations.

For a product that appears in the test split but was never seen in
train, there's no train-derived average to give it -- fall back to
something you DO have from train (the overall train mean of the target is
the natural choice, the same way an unseen category level falls back to
"unknown" in a one-hot scheme).
