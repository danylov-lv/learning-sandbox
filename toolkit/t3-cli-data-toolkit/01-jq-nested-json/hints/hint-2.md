# Hint 2 — mechanism

- **Join**: build a lookup object from `sources.json` first —
  `map({(.source_id): .tier}) | add` turns the array into
  `{"s1": "gold", ...}` you can index directly.
- **Flatten + carry the join key down**: for each page, its `source_id`
  (and therefore tier) applies to every listing inside it. Attach the tier
  to each listing *before* you flatten pages away, e.g. by mapping each
  page's listings and merging in `{tier: ...}` per listing, then
  collecting all pages' listings into one flat array (a nested `map(...)`
  producing arrays of listings, piped into `add` or `flatten`, does this).
- **Group + aggregate**: `group_by(.category)` needs its input already
  sorted by that key or it will silently mis-group — `group_by` itself
  sorts, so that's handled, but remember it returns an array of arrays
  (one array per category), not the array of summary objects you need —
  you still have to `map` over the groups to reduce each one down.
- **tier_counts with all three keys present**: start from a fixed object
  `{gold:0, silver:0, bronze:0}` and increment into it with `reduce`,
  rather than building the object only from tiers that actually occur in
  that group.
