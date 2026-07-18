Before you write any statistics code, just look. Load the valid USD prices
(filter `price` not NaN, `price > 0`, `currency == "USD"` from
`harness.common.load_observations()`), and plot a plain histogram of them
in a scratch script or notebook -- not even the `make_figure` function yet,
just `plt.hist(prices, bins=100)`.

Look at the shape. Where does the bulk of the mass sit relative to where
the x-axis extends? How far does the tail stretch compared to how wide the
main hump is? Would you describe this shape as symmetric?

Then do the same thing to `np.log(prices)`. Compare the two shapes by eye
before you compute a single number. The numbers you'll compute later
(skewness, kurtosis, a test statistic) are there to quantify something you
should already be able to see.
