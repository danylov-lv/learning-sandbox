Before writing any code, look at what `baseline_features` actually uses:
`seller_rating`, `in_stock`, hour-of-day. Now look at the full column list
in the observations DataFrame -- `category`, `title`, `price`, `currency`,
`scraped_at`, `in_stock`, `seller_rating`, `source_site`, `discount_pct`,
`units_sold`. Which columns got left out of the baseline?

Two of them got left out for a boring reason: they're strings, not numbers
-- `category` and `title`. A regressor can't multiply a coefficient by the
word `"electronics"`. That doesn't mean they carry no information; it means
nobody has turned them into numbers yet. That's the whole task.

If you want a starting intuition for how much signal is hiding in
`category` alone: go look at `generate.py` (or just eyeball a few rows of
the dataset grouped by category) and notice how differently priced an
"electronics" row looks compared to a "books" row. That gap, currently
invisible to a regressor because it's locked inside a string column, is
most of what you're about to unlock.
