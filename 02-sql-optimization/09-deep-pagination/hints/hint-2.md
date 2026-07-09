# Hint 2

Instead of asking "give me rows N through N+100 of this ordering," ask "give
me the next 100 rows after the last one I already saw." That second
question doesn't need a position/offset at all — it needs a value to
compare against, remembered from the previous page. That value is usually
called a cursor or a seek key, and this style of pagination is called
keyset pagination.

The complication: your seek key here isn't a single column. `occurred_at`
has ties (multiple events landed in the same second), so "give me
everything after this timestamp" is ambiguous at a page boundary that falls
inside a tied group — you'd either skip rows that share the boundary
timestamp, or return some of them twice on the next page. What two-column
comparison would you need to make the "next row" relation well-defined and
match `ORDER BY occurred_at DESC, id DESC` exactly?
