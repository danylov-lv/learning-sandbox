# Design: Price monitoring at 10,000-site scale

## Requirements and SLOs

[fill in: functional requirements (what the system must do), the three
freshness tiers and what SLO each one promises, availability target,
and anything explicitly out of scope. Be quantitative — name the tier
intervals and the fraction of the URL set each tier covers.]

## Architecture

[fill in: the major components (scheduler, fetch workers, proxy layer,
parse workers, storage, observability) and how they connect. Name the
concrete mechanisms you'd actually deploy — queue technology, worker
pool model, proxy rotation strategy, autoscaling trigger — not just
boxes and arrows in prose.]

## Scheduling and freshness

[fill in: how URLs get enqueued on their tier's cadence, how you avoid
thundering-herd alignment at cadence boundaries, how retries are
scheduled relative to the next regular fetch, and how a missed or
delayed fetch is reconciled against the freshness SLO.]

## Data flow

[fill in: the path of one URL from scheduling trigger through fetch,
parse, price-change detection, and storage/downstream delivery. Note
where backpressure applies if a downstream stage falls behind.]

## Capacity model

[fill in: walk through your `src/estimate.py` results in prose — the
daily fetch volume, the peak throughput, the required concurrency and
pod count, the egress volume, and the monthly proxy cost implied by the
committed `workload.json`. State the actual numbers, not just "we
computed them."]

## Bottlenecks and failure modes

[fill in: where does this design break first as load grows — proxy
pool, parse CPU, a shared queue, a database write path? What happens to
the rest of the system when that component is degraded rather than
fully down? Use the `parse_cpu_ms_per_page` figure from the workload to
reason about whether parsing or fetching is the tighter constraint.]

## Evolution at 10x

[fill in: what changes at 10x the URL count — does the architecture
still hold, or does a component need to be re-designed rather than just
scaled up? Be specific about which piece breaks first and what replaces
it.]

## Hostile review responses

[fill in: this section holds the answers to HOSTILE-REVIEW.md's Q1-Q8,
each as its own `### Qn` subsection below. Restating the question is not
an answer.]

### Q1

A target site changes its markup. The fetch still returns `200 OK` with
a normal-looking response size, so nothing in your retry or
health-check logic sees a failure — but the parser's price selector no
longer matches, and every extraction for that site silently returns
null or zero from now on. How does your system detect this class of
failure, which never shows up as a fetch error, a timeout, or a
non-200 status?

[fill in]

### Q2

Your hot tier refreshes every 15 minutes. If every hot-tier URL is
scheduled on the same wall-clock grid (`:00`, `:15`, `:30`, `:45`), what
actually happens to your fleet, your proxy pool, and the target sites'
rate limits at each of those boundaries? Walk through the mechanism
that prevents this, concretely — not "we add jitter" as a slogan, but
where the jitter is applied and what bounds it.

[fill in]

### Q3

You've defined a freshness SLO. Explain exactly what event you
timestamp, what "stale" means as a threshold on that timestamp, and
then describe how you would prove, from production telemetry alone,
that the SLO was met (or missed) for a given tier over the past 24
hours — without re-deriving the capacity model from scratch to
reconstruct what should have happened.

[fill in]

### Q4

Your proxy pool doesn't fail outright — it degrades. Egress starts
taking 3-4x longer per request and your success rate on first attempt
quietly drops. Nothing pages anyone because nothing is down. What is
the first component in your architecture to fall over, and how does
the rest of the system behave in the minutes after that — does it
degrade gracefully or cascade?

[fill in]

### Q5

Your capacity model treats the URL set as a uniform pool split into
three tiers by fixed fractions. In reality, site-to-site URL counts are
Zipf-distributed — a handful of large catalog sites contribute a
wildly disproportionate share of the URLs in any given tier. What
actually happens to a single oversized site's freshness and to your
per-site politeness budget when it alone accounts for, say, 4-5% of the
entire hot tier?

[fill in]

### Q6

Your retry math assumes each attempt is an independent trial with a
fixed success probability. But a real failure mode is a site IP-banning
your egress range specifically — every subsequent attempt against that
site from that proxy is now correlated, not independent, and retrying
just burns egress for a certain failure. How would your system tell
"this is a transient, independent failure, retry as planned" apart from
"this proxy/site pair is burned, stop retrying and do something else,"
and what does it do differently in the second case?

[fill in]

### Q7

You poll every URL at a fixed cadence per tier regardless of how often
its price actually changes. Quantify the two failure directions this
causes: a cold-tier URL that has a flash sale and changes price five
times in an hour (what does your system report as "the price" for that
hour?), and a hot-tier URL whose price never changes for weeks (what
did those extra fetches buy you)? Would a fixed cadence per tier
survive contact with real price-change frequency data, or does the
design need something adaptive?

[fill in]

### Q8

A downstream team says your freshness numbers "don't add up" for a
specific day last week — they claim prices they pulled were staler
than the SLO promises. Without access to you, walk through what
dashboards, logs, or stored metrics would need to already exist for
someone on-call to reconstruct exactly what the fleet was doing that
day, tier by tier, and confirm or refute the claim.

[fill in]
