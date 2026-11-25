Before touching Redis, get clear on exactly what work is being repeated and
why it's expensive.

Every call to `GET /categories/{id}/summary` runs the same aggregation over
`shop.products` for that category. Nothing about the answer depends on the
request beyond the `category_id` -- two requests for the same category, one
second apart, do identical scans and get identical results. That is the
signature of something cacheable: a pure-ish function of a small key, called
far more often than its inputs change.

The expensive part is the Postgres round-trip and the aggregation itself,
especially for a large category. The cheap part -- looking up a value you
already computed -- is what Redis is for. So the shape of the fix is: before
doing the expensive thing, ask "have I already got the answer for this
`category_id` sitting somewhere fast?" If yes, return it and skip the
database entirely. If no, do the work, but stash the answer so the next
caller can skip it.

The two handlers mirror each other: the GET populates and reads that stash;
the invalidate endpoint removes an entry from it. Everything else is detail.
The next hint names the pattern and its exact steps.
