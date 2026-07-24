# Hint 3 — concrete approach

Shape of the pipeline (fill in the pieces yourself — this is structure,
not a working filter):

1. `--slurpfile sources ...` gives you `$sources[0]` as the array; reduce
   it to a `source_id -> tier` object.
2. `--slurpfile catalog ...` gives you `$catalog[0].pages` as the array of
   pages. For each page, `.listings | map(. + {tier: <lookup>[$p.source_id]})`
   produces that page's listings with the tier merged in. Doing this
   inside `map($catalog[0].pages[]; ...)` (or an equivalent `as $p |`
   binding) and then flattening the per-page arrays into one array is the
   "flatten nested arrays" step.
3. `group_by(.category)` on the flat array, then `map(...)` each group
   into `{category, listing_count, avg_price_usd, tier_counts}` using
   `length`, `map(.price_cents/100) | add / length`, and a `reduce` over
   `{gold:0,silver:0,bronze:0}` for the tier counts.
4. The whole thing is one `jq -n --slurpfile ... --slurpfile ... '<pipeline>'`
   invocation (`-n` because you're not piping a third file into stdin —
   both inputs come in via `--slurpfile`).

Pipe the output of each intermediate stage into `jq .` by itself while
building this up, so you can see what each `as $x` binding actually
contains before trusting the next stage.
