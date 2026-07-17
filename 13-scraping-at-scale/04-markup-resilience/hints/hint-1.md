Every extractor you've ever written that used exactly one CSS selector per
field was implicitly betting that the page will always look the way it
looked when you wrote the selector. That bet is fine right up until a
redesign, an A/B test, a migration to server components, or -- as here --
the site simply serving different templates to different products. When the
bet loses, a brittle extractor doesn't crash. It returns `None` and moves
on, silently. Nobody notices until someone downstream asks why a third of
the catalog has no price.

The fix isn't a smarter selector. It's accepting that no single selector,
however clever, is going to be reliable forever or everywhere -- and
building the extraction so that failure of any one path is expected and
survivable. For each field you need, decide on more than one independent
way to find it on the page, order them from "most likely to be right when
present" to "last resort," and take the first one that actually produces a
value.

Before you write a single selector, go look at the four different `?v=`
renderings of the same product yourself (`curl` or a browser) and notice
what's genuinely the SAME piece of information expressed in different
shapes -- a price that's sometimes visible text, sometimes a machine-
readable attribute, sometimes buried in a script tag. That's the shape of
the problem you're solving, before you write any code to solve it.

Once you have per-field fallback chains, measure them: for a batch of
extracted records, what fraction actually got a non-null value per field?
That number, watched across a sample that spans every template the site
serves, is how you'd notice a chain quietly failing on one whole encoding
in production -- long before a validator (or an angry stakeholder) tells
you.
