# Hint 2 -- narrowing to a mechanism

`materialize()` is the whole ballgame. Everything else in this capstone
(`produce`, `ensure_group`, `run_consumer`, `reclaim_and_run`) is plumbing
that gets entries to `materialize()`, possibly more than once, possibly out
of their original relative order. `materialize()` is what has to make that
safe.

Think about what "keep the latest observation per product" actually means
as a comparison, not just an upsert. Two events for the same product_id
don't arrive at `materialize()` in chronological order just because they
arrive in stream order -- the stream is built by shuffling events (see
`.authoring/design.md` once you've read it), so `event_id` order and
`scraped_at` order are independent. That means:

- Comparing only `scraped_at` isn't quite enough on its own -- two events
  can land in the same second. You need a tiebreaker that makes "newer"
  a strict, unambiguous total order. `event_id` is unique and 1..N; use it
  as the tiebreaker.
- "Keep whichever arrived at `materialize()` most recently" is wrong,
  full stop -- that's delivery order, not observation order, and this
  capstone's data is built specifically so those two orders disagree often
  enough that a shortcut here gets caught.
- "Skip if this product_id already has a document" is ALSO wrong, in a
  more subtle way: it optimizes for "don't double-process a duplicate,"
  but it also means a legitimately newer observation that happens to arrive
  for a product that already has SOME document gets silently dropped. The
  crash/reclaim checkpoint is specifically built to expose this -- some
  products get their first materialized observation from work done before
  a simulated crash, and a genuinely newer observation for those same
  products only shows up in what gets reclaimed afterward. An
  existence-check "dedup" would keep the stale one forever.

The comparison that's actually correct is: for a given product_id, is THIS
entry's `(scraped_at, event_id)` greater than what's currently stored (or is
nothing stored yet)? If yes, apply it. If no, it's a no-op -- whether
because it's a plain duplicate redelivery of something already applied, or
because it's a stale observation racing a fresher one. Look at what MongoDB
gives you for expressing "the new value depends on comparing it to the
document's OWN current value" in a single update call, rather than reading
the document in application code first and writing back (which reintroduces
exactly the check-then-act gap task 01 warned you about, just against
Mongo instead of Redis).
