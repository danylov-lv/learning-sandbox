A held-out score that looks too good to be true usually means the test set
influenced training somewhere -- directly or indirectly. The model can't
literally see the test labels during `.fit()`, but a FEATURE can carry
information about a test row's own target if that feature was computed
using the test row's own data before the split ever happened.

Look at the feature-engineering step, not the model. Specifically: any
time you aggregate something BY an id column (a per-product average, a
per-user rate, a per-store count) and then use that aggregate as a
feature, ask "which rows contributed to this average, and does that set
include the row I'm about to predict?" If the answer is yes, and if the
group the row belongs to is small, that row's own target is doing a lot of
the work in its own feature.

`product_id` in this dataset has ~8000 distinct values across ~60000
observations -- most products have only a handful of rows. Averaging
something over a group that small, using ALL of that group's rows
including the ones you're about to test on, is exactly the shape of this
trap.
