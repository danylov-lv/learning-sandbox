Read `src/naive.py` closely before writing any numpy -- not to copy its
logic, but to notice its *shape*: every function does the same three-step
thing (figure out something per group or per window, then look that
something up for every row). The row-by-row loop is what you're removing;
the three-step shape underneath it is what you're keeping.

Try to stop thinking "for each row, do X" and start thinking "what's true
of the whole array at once." `prices - prices.mean()` is already a
whole-array operation over the WHOLE array -- the actual task is getting
that same idea to work *within each group* instead of globally, and
*within each window* instead of over the whole array. Both of those are
solved problems in numpy; you don't need a custom trick for either, you
need the right built-in.

Don't reach for `np.vectorize` or `pandas.Series.apply` -- both still call
a Python function once per element under the hood. They'll pass a
"my code has no explicit `for` keyword" smell test without actually fixing
the thing that makes the naive version slow.
