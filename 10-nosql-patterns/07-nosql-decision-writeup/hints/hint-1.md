# Hint 1

Before writing prose, make a table. Rows: rate limiter, distributed lock,
Bloom dedup, streams consumer group, Mongo document model, Mongo-vs-JSONB.
Columns: what problem it solves, what Postgres would have to do to solve
the same problem, and why that's awkward or expensive in Postgres
specifically (not "Postgres is slow" — name the actual mechanism: a
check-then-act race, a lack of a durable ack/redelivery primitive, a
memory-vs-accuracy tradeoff a b-tree can't make for you).

Notice that four of those six things (01-04) aren't really "storage"
questions at all — they're coordination and shape questions Redis happens
to answer well because of specific data structures (atomic counters, `SET
NX`, a probabilistic filter, a log with consumer-group bookkeeping). Keep
that distinction sharp: it's the difference between "Redis as a data
structure server for coordination" and "Redis as a place you keep your
system of record." Don't write the memo yet. Just fill in the table.
