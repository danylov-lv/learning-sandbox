# Hint 3

For "Three concrete calls," pick scenarios that force different answers —
if all three of your scenarios land on the same engine, you haven't found
the axes yet. Think about your own scraping domain and try shapes like:

- A brand-new low-volume category feed, one analyst poking at it a few
  times a week, data already sitting as Parquet from the scraper's export
  step. What did task 06/07 teach you about that shape?
- A dashboard multiple people on the pricing team hit throughout the day,
  fed by continuous scraper ingest, where yesterday's data needs to age
  out automatically. What did tasks 02/04 teach you about what that
  requires operationally?
- A small internal one-off: "did this seller's price change last week,"
  a few thousand rows, asked twice a month. Does this need an analytical
  engine at all, or is Postgres — with no changes — already fine?

For each, write the decision, then justify it by naming what you'd measure
again to confirm — e.g., "the task 05 ratio was large enough that even at
1/10th this volume, Postgres would still lose" or "the task 07 gap was
small enough on a single reader that the ops cost of a server isn't worth
it here."

For "What surprised me," it's fine if the honest answer is small — e.g.
"I expected the primary index to matter more than it did until the query
actually matched the ORDER BY," or "I didn't expect DuckDB to get this
close without a server," or "TTL turned out to be simpler to reason about
than the materialized view was." Write the one that's actually true for
you, not the one that sounds impressive.
