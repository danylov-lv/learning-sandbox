Start by getting the shape right before you worry about correctness of any
single number.

Read `src/metrics.py`'s docstring slowly. It hands you seven metric families
with their exact names and label sets -- your only job in that file is to
pick the right `prometheus_client` type for each and construct it. Three of
them are running totals that only ever go up (pages fetched, records
quarantined, fetch errors, honeypot hits) -- those are Counters. One is a
point-in-time fraction that can move either way per field (field
completeness) and one is a 0/1 flag (banned) -- those are Gauges. One is a
distribution of per-request durations (fetch latency) -- that's a Histogram.
Which ones carry a label, and what the label is called, is spelled out in the
docstring; get those strings byte-exact.

Then look at `src/serve.py`'s docstring. It describes a very specific crawl
the validator is written against: two client identities, a paced loop over
product ids 1..300 hitting two endpoints per id, and a `/metrics` server that
keeps running afterward. Don't invent a different structure -- fill in the one
described.

Before writing the crawl, prove to yourself you can expose an endpoint at all:
build the metrics, bump one counter by hand, start `prometheus_client`'s HTTP
server on 9113, and curl `http://127.0.0.1:9113/metrics`. Once you see your
counter in that text output, you know the plumbing works and everything else
is just moving real numbers through it.

The dashboard is a separate, smaller deliverable -- don't leave it for the
very end and be surprised the validator wants it. It only needs to be a JSON
file with a `panels` array that mentions at least three of the spider metric
names. You can build it in the Grafana UI at `http://localhost:3313` and
export it, or hand-write a minimal one.
