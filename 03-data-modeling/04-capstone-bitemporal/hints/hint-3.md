# Hint 3 (q12 + pulling the whole battery together)

For q12: a listing's status right now is entirely determined by its *most
recent* lifecycle event (discovered / delisted / relisted, in
`event_time` order) — not by counting how many times it's been delisted
or relisted. "Delisted during 2025 and never relisted since" means: look
at each listing's very last lifecycle event as of the end of the stream;
keep it only if that last event is a delist and its `event_time` falls in
2025. Anything that has a later relist doesn't qualify, no matter how many
times it churned earlier. A window function that ranks each listing's
events by `event_time` descending and keeps rank 1 gets you that "last
event" directly.

Before you call CP2 done, run through this checklist against every query
in the battery — these are the failure modes that tend to hide inside an
otherwise-plausible-looking result set:

- **Duplicate rows from missed dedup.** Anywhere you touch raw
  `price_observed` rows instead of your deduplicated view/table, check
  whether an exact-duplicate pair could double-count into an aggregate or
  a window function.
- **Current-state joins where as-of was required.** Any question that says
  "as-of the observation's own event_time" (q09, q10, q11, q13b, q15) is
  wrong if it joins to a dimension's *latest* row instead of the row valid
  at that specific timestamp. This is the easiest place for a correct-CP1,
  correct-star-schema answer to still silently regress once you wire
  things together.
- **Ingest-cutoff filters applied to the wrong timestamp.** A predicate
  like `ingested_at <= cutoff` filtering on `event_time` instead (or vice
  versa for the "all data" column of q13b) produces a plausible-looking
  but wrong number, not a query error — nothing will crash to warn you.

Running `--all` after each fix (not just the question you touched) is
cheap insurance against exactly this class of regression.
