# Design: Price History Storage

## Requirements and access patterns

[fill in: restate the problem in your own words -- what has to stay
queryable, for how long, and the three access patterns (charting read,
analytics read, write firehose). Name which one dominates and which one is
allowed to be slower/more expensive. Cite at least the tracked-product
count and the retention window from workload.json.]

## Physical layout

[fill in: the schema (columns, types), the partitioning scheme (grain and
key), and the ordering/clustering key -- and why that specific column order,
not some other. Say explicitly which read pattern the key was chosen for
and what that decision costs the other pattern.]

## Write path

[fill in: how the continuous firehose of scrape observations lands --
batching, buffering, file/part sizing, and how out-of-order or late writes
are handled before they're durable.]

## Read paths

[fill in: how the charting read (one product, a date range) is served by
the physical layout above, and how the analytics read (top-N movers per
category per day) is served -- are they the same table, a materialized
view, a separate rollup? Justify with the bytes-scanned numbers from your
capacity model.]

## Capacity model

[fill in: walk through what `src/estimate.py` computes and what the
numbers mean in plain language -- rows/day, total retained rows and bytes,
the change-only alternative and whether it's worth it, hot-tier size, and
monthly storage cost. Reference the actual numbers your functions produce
on the committed workload.json.]

## Retention and tiering

[fill in: the hot/cold boundary, what physically moves (or doesn't) at
that boundary, and what enforces the 5-year retention cutoff at the far
end -- expiry, compaction, or something else.]

## Bottlenecks and failure modes

[fill in: where this design breaks under load or under an awkward access
pattern -- compaction falling behind, a hot partition, a skewed category,
a slow cold-tier read that a client mistook for a charting-read SLA.]

## Evolution at 10x

[fill in: which part of this design is the first to need rework at 10x the
tracked-product count, and what you'd change.]

## Hostile review responses

[fill in: a one-line intro if you want one -- the substance goes in the
Q1..Q8 subsections below. Each restates its question, then answers it.]

### Q1

[fill in: restate Q1, then answer it.]

### Q2

[fill in: restate Q2, then answer it.]

### Q3

[fill in: restate Q3, then answer it.]

### Q4

[fill in: restate Q4, then answer it.]

### Q5

[fill in: restate Q5, then answer it.]

### Q6

[fill in: restate Q6, then answer it.]

### Q7

[fill in: restate Q7, then answer it.]

### Q8

[fill in: restate Q8, then answer it.]
