# Hint 1

A Deployment answers "keep N copies of this running forever, replacing
any that die." A Job answers a completely different question: "run this
a specific number of times, to completion, then stop." There's no steady
state to maintain — a Job that's done its work is *supposed* to have no
running pods left, and that's success, not a problem to alert on.

Two fields decide the shape of "run this a specific number of times":

- `completions` — how many pods must exit `0` in total before the Job is
  considered done. Think of it as "how many shards exist."
- `parallelism` — how many of those pods are allowed to run at the same
  time. Think of it as "how many workers process shards concurrently."

`completions: 4, parallelism: 2` doesn't mean "run 2 pods, twice, forever
until it feels like 4" — it means the Job controller keeps at most 2 pods
running at any moment, launching a new one whenever one finishes
successfully and the total-succeeded count is still under 4, until all 4
have succeeded. If you set `parallelism` equal to `completions`, every
shard starts at once; if you set it to `1`, shards run strictly one after
another — you have both extremes and everything between available.

The CronJob wraps this same idea in a scheduler: it's not a different
kind of workload, it's a factory that creates a Job (from `jobTemplate`)
each time its `schedule` fires. Everything you learn about Job fields
here transfers directly into `jobTemplate.spec`.
