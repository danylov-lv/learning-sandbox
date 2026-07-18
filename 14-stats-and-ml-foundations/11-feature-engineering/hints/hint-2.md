Four separate transformations, one per raw column family:

1. **`category`** is a string with a small, fixed set of values. Turn each
   distinct value into its own 0/1 column -- "one-hot encoding." Don't turn
   it into a single integer column (0 for "apparel", 1 for "books", ...
   whatever order); that implies a numeric ordering between categories that
   isn't real, and a linear regressor will happily (and wrongly) fit a
   trend across that fake ordering. Pandas has a one-line function for
   exactly this.

2. **`source_site`** -- same treatment, same reasoning, fewer distinct
   values.

3. **`scraped_at`** is already a proper pandas datetime column (check its
   dtype). It has an accessor namespace built specifically for pulling
   calendar parts back out of a timestamp -- day of week, month, hour are
   all one-line extractions from it. "Is this a weekend" is just a
   comparison on the day-of-week value you already extracted.

4. **`title`** is free text. The cheapest useful features are things you
   can compute with plain string methods on the whole column at once:
   how long is the string, how many words does it have, how many digits
   does it contain. A step up from that: scikit-learn has a vectorizer
   built for exactly "turn a column of text into a matrix of word-based
   numeric features" -- look in `sklearn.feature_extraction.text`. Cap how
   many features it produces; you don't need (or want) one column per
   distinct word ever seen.

Once you have all four pieces as arrays (or columns), you need to combine
them into one matrix with the same row count and row order as `df`. If
everything is dense (plain numbers, no text vectorizer), pandas
`pd.concat(..., axis=1)` or `np.column_stack` both work. If you used a text
vectorizer, its output is sparse, and mixing sparse with dense needs a
different combining step -- see hint 3.
