# NOTES

## Observed results

(fill in -- the counts you got for the containment query and the nested
color query on both sides, and what the EXPLAIN / explain() plans actually
showed once indexed: the Postgres plan's scan type, the Mongo plan's stage
tree)

## Verdict: query ergonomics

(fill in -- `doc @> '{...}'::jsonb` vs the Mongo filter for the containment
query; `doc->'specs'->>'color'` vs `specs.color` for the nested match.
Which was easier to read, write, and would be easier to extend?)

## Verdict: in-place update

(fill in -- `jsonb_set` vs `$set` on a dotted path. Did either surprise you
about what it rewrites under the hood, or how it behaves under concurrent
writes to different fields of the same document?)

## Verdict: index flexibility

(fill in -- what you actually built on each side, and what would have to
change on each side if a sixth predicate field showed up in tomorrow's
query)

## Verdict: aggregation

(fill in -- if you also did task 05, compare its Mongo aggregation
pipeline to the equivalent Postgres SQL over `doc->>'field'` expressions)

## Verdict: operational cost

(fill in -- running and maintaining a second database engine vs one more
index type/query pattern on a database you already run. Which cost did
this task make more concrete?)

## When would you actually reach for JSONB instead of a document database?

(fill in -- your honest answer, in one or two sentences, now that you've
built the same thing both ways)

## Gotchas

(fill in after completing the task)

## Open questions

(fill in after completing the task)
