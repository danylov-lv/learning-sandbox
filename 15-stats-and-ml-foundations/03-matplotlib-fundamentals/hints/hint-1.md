Start with how you create the figure, before worrying about what goes in
each panel.

`plt.subplots(2, 2, figsize=(...))` gives you back `(fig, axes)` where
`axes` is a 2x2 numpy array of `Axes` objects -- one per grid cell. From
here on, every drawing call goes through one of those four `ax` objects
(`ax.hist(...)`, `ax.boxplot(...)`, `ax.plot(...)`, `ax.bar(...)`,
`ax.set_title(...)`, `ax.set_xlabel(...)`, `ax.set_xscale(...)`), never
through bare `plt.hist(...)` / `plt.title(...)` / `plt.xlabel(...)`.

Why this matters here specifically: pyplot's top-level functions
(`plt.plot`, `plt.title`, etc.) operate on whatever the "current axes" is --
a piece of global, mutable state that gets set as a side effect of the last
thing you drew. With one chart that's invisible and convenient. With four
charts on one figure, it becomes a bug generator -- call `plt.title(...)`
at the wrong moment and your label lands on the wrong panel, with no error
telling you so. The object API (`fig`, `axes[i, j]`) sidesteps this
entirely: every call is explicit about which panel it targets.

`axes` is a 2D array, so you'll index it as `axes[0, 0]`, `axes[0, 1]`,
`axes[1, 0]`, `axes[1, 1]` (or flatten it with `axes.flat` / `axes.ravel()`
if you'd rather loop). Which panel goes in which grid cell is entirely your
call -- the validator only checks that there are exactly 4 Axes total and
that each one is fully labeled, not their arrangement.
