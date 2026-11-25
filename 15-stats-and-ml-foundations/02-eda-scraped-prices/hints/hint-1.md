Before you write a single aggregate, look at the raw data with your own
eyes. Open a REPL, load it, and just look:

```python
from harness.common import load_observations
df = load_observations()
df.shape
df.head()
df.dtypes
df.isna().sum()
df["price"].describe()
```

You're trying to build an intuition for three things before you commit to
any code: how big this table is, which columns can be missing or wrong
(price and currency are the ones that matter here), and roughly what shape
the price distribution has (hint: it will not look like a bell curve --
real-world prices rarely do). Notice how many rows have a NaN price, how
many have a non-USD currency, and whether any prices look suspiciously
small, suspiciously large, or negative. You don't need to fix any of that
in this task -- just notice it. The next task in this module goes deeper
into *why* prices aren't normally distributed, and a later one teaches you
to tell a genuine outlier from a parsing defect. Here, your job is smaller:
count things accurately and describe what you see.
