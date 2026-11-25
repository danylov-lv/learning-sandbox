# When NoSQL Beats Relational, and When It Doesn't — Decision Memo

Fill in each section with your own analysis, grounded in what you built and
measured across tasks 01-06 of this module.

## Redis beyond cache — what each primitive buys you

[fill in — for the rate limiter (01), the distributed lock (02), Bloom
dedup (03), and the streams consumer group (04): what coordination problem
does each one solve that a relational database handles poorly or not at
all? Name the actual primitive each relies on (atomic check-and-record,
fencing token + compare-and-delete, probabilistic set membership,
XACK/XAUTOCLAIM) rather than just asserting "it's fast".]

## MongoDB vs Postgres JSONB

[fill in — where did the document store genuinely win in tasks 05/06, and
where did Postgres JSONB with a GIN index already give you the same answer
with one engine instead of two? Be specific about index shape and query
shape, not just "Mongo is more flexible".]

## When to just use Postgres

[fill in — Postgres is the default. What has to be true about a workload
before you'd reach for Redis or Mongo instead? What did tasks 01-06 teach
you about the operational floor below which a second engine is pure
overhead with no payoff?]

## Operational and consistency costs

[fill in — running Redis and/or MongoDB alongside Postgres: what do you now
own that you didn't before (durability across a restart, failover, backup,
monitoring)? What consistency model does each store actually give you, and
where would a gap in it bite in a scrape-ingestion pipeline — duplicate
writes, a lost lock, a stale materialized document?]

## Decision checklist

[fill in — a short, bulleted heuristic you would actually apply the next
time someone proposes a new datastore. Should read like something you'd
paste into a design doc, not a restatement of the sections above.]
