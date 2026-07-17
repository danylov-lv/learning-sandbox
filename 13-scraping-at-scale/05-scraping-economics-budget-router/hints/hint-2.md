The signal is `review_count`. It's rendered as plain visible text on every
one of the 4 markup versions this target serves (a `.reviews` div, a `.rc`
span with the number in parens, a `.rv` div, a `.rv` paragraph -- same
number, four different wrappers) -- so it's always available from the
cheap HTML fetch, never behind the render step.

Why does that make it the right gate? Because `rating` and `shipping_info`
are only meaningful for a product that has reviews in the first place: a
product with `review_count == 0` has nothing to show for either field, so
rendering it to go fetch them buys you nothing -- it's the same wasted
`API_EXTRA_COST` as rendering a product that already had everything it
needed from the cheap fetch. A product with `review_count > 0`, on the
other hand, is missing real data until you render it, and that's exactly
what the completeness check is measuring.

So the per-product decision is a single branch on one number you already
have after step 1. Account for cost the same way the validator will:
every product pays the html cost once; only the products you actually
call the render endpoint for pay the extra render cost on top.

Extracting that one number reliably across 4 differently-shaped pages is
its own small problem -- the next hint gets concrete about the shape of a
router that handles it.
