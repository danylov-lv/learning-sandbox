# Scraping economics -- budget router analysis

Fill in every section below. `tests/validate.py` checks that each section
header exists, that no placeholder marker (`[fill in`, `TODO`, `TBD`) is
left anywhere in this file, and that the per-1M-pages table mentions all
three strategies -- it does not grade your prose, but it does require the
sections to actually be substantive.

## Cost model assumptions

[fill in: state the modeled costs you're working from (HTTP fetch cost,
render/API extra cost, what "render" stands for in this model), the
completeness target, and the observed render fraction your router settled
on for this catalog -- and why that fraction is roughly what you'd expect
given how `review_count` is distributed.]

## Per-1M-pages cost by strategy

[fill in: a markdown table with one row per strategy (all-http, all-render,
mixed) showing at least the per-1M-pages cost from `project_per_million`,
and the completeness each strategy achieves. Something like:

| strategy   | completeness | cost per 1M pages |
|------------|--------------|--------------------|
| all-http   | ...          | ...                |
| all-render | ...          | ...                |
| mixed      | ...          | ...                |

Fill in real numbers computed from your own `costmodel.py` and the render
fraction your router actually achieved -- not placeholders.]

## When to render vs not

[fill in: under what conditions is paying the render cost for a product
worth it, and when is it pure waste? Generalize past this specific
catalog's `review_count` gate -- what property would make a similar
render-or-not decision worth building into a different scraper?]

## Recommendation

[fill in: which strategy would you actually ship, and why -- tie it back
to the completeness target and the cost numbers above, not just intuition.]
