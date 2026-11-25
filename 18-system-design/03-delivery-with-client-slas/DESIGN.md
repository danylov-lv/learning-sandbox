# Design — delivery pipeline with per-client SLAs

## Requirements and SLA/SLO definitions

[fill in: define, per tier (gold/silver/bronze), the SLI you will actually
measure (e.g. "minutes between record scraped and record delivered"), the
SLO you hold internally, and the SLA you sell — and say explicitly why
those three are not the same number. State each tier's freshness deadline,
monthly availability target, and what "available" means operationally
(a delivery attempt succeeded? a client's webhook returned 2xx? a batch
cleared within its deadline?). Name the functional and non-functional
requirements (throughput, durability, ordering guarantees, exactly-once vs
at-least-once) and the explicit non-goals.]

## Architecture

[fill in: the end-to-end path from a scraped record to a delivered one —
crawl/ingest, normalization, per-client contract matching, a shared
priority queue or scheduler under the crawl/delivery budget, the delivery
workers per transport (webhook push, SFTP drop, S3/object-storage pickup,
API pull), retry/dead-letter handling, and the breach-detection/reporting
path that watches all of the above. Name every component and what talks to
what. State where state lives (queue depths, delivery receipts, retry
counters) and why.]

## Contracts and schemas

[fill in: what a per-client contract record looks like (tier, freshness
deadline, availability target, delivery transport, batch size, penalty
terms) and where it is stored/enforced. What the wire schema for a
delivered batch looks like, how you version it, and how you tell a client
"this batch is a resend, not a duplicate" (or vice versa) at the schema
level.]

## Prioritization under a shared budget

[fill in: the crawl budget and delivery capacity are shared across all
clients and tiers. Name the scheduling policy (e.g. weighted fair queuing,
strict priority with anti-starvation floor, deadline-aware scheduling) and
say precisely what happens to a lower tier when a higher tier's demand
spikes. Make the starvation tradeoff explicit — who loses service first,
by design, and how that is different from an emergent side effect nobody
decided on.]

## Delivery, retry and replay

[fill in: the retry policy per transport (backoff shape, max attempts,
what happens after exhaustion), how you tell delivered-once from
delivered-twice (idempotency key, dedup window), and how a client replays
a window of history after their own outage without you re-scraping
anything. State what "exactly-once delivery" actually means here versus
what you really provide (idempotent at-least-once) and why that
distinction matters to the SLA.]

## Capacity model

[fill in: walk through, in prose, what `src/estimate.py` computes and why
each formula is shaped the way it is — total daily volume, average and
peak delivery rate, the error budget per tier, backlog growth during an
outage, and drain time afterward. Reference the actual numbers your model
produces for the committed `workload.json` (do not just describe the
formula — state the resulting figures) and say what they imply about
current headroom.]

## Breach detection and reporting

[fill in: how a freshness or availability breach is detected in near-real
time (not discovered a month later at invoicing time), what triggers an
internal alert versus a client-facing notice, and how the monthly penalty
report is generated and reconciled against what the client's own logs
would show. Say what "observed breach" means operationally and who signs
off on it before it becomes a line item.]

## Bottlenecks and failure modes

[fill in: name the actual bottleneck in the shared pipeline today (crawl
budget? delivery worker fleet? a single downstream rate limit?) and at
least two concrete failure modes beyond "the outage scenario" — e.g. a
poison-pill record that jams a batch, a client's schema change that breaks
delivery silently, a thundering-herd retry storm after a shared dependency
recovers.]

## Evolution at 10x

[fill in: at 10x today's client count and record volume, what breaks
first, and what changes structurally (not just "add more workers") —
does the priority scheme still hold, does the shared budget model still
make sense, does per-tier error-budget tracking need to become per-client,
does a single shared delivery fleet need to split by tier or by transport.]

## Hostile Review

### Q1

Under the shared crawl budget, when there is not enough crawl capacity to satisfy every tier's freshness deadline at once, who gets starved, and how does your design make that an explicit engineered choice rather than an emergent property of whichever queue happens to drain first?

[fill in]

### Q2

A record is delivered inside the freshness deadline but the underlying page it reflects was scraped three hours ago because the upstream site was slow to change: does that count against the freshness SLA, the availability SLA, neither, or both, and why does that distinction change which number moves on the penalty invoice?

[fill in]

### Q3

A gold-tier client's ops team emails that sixty of their deliveries missed the 15-minute deadline last month and disputes your invoice line item: what evidence do you have, and specifically what evidence do they not have, to settle the dispute per delivery rather than per vibe?

[fill in]

### Q4

A client's own webhook endpoint or SFTP drop goes down for six hours: walk through exactly what happens to your retry queue during those six hours, and how you stop one client's downstream outage from consuming crawl or delivery budget the other tiers are contractually owed.

[fill in]

### Q5

Is the error budget you track measured per client or per tier, and name one concrete situation where aggregating to the tier level hides a real problem, either one client dragging a tier's average into breach while the rest are fine, or the reverse.

[fill in]

### Q6

Your drain-after-outage math assumes the pipeline can run at its full rated drain capacity while simultaneously serving live traffic: what concretely throttles that in practice, and what happens to your recovery-time number if that assumption is off by 2x?

[fill in]

### Q7

Bronze-tier clients silently absorb most of the backlog after an incident because gold and silver get priority under the shared budget: do bronze clients know in real time that they have been deprioritized, and what has to be true commercially before that deprioritization happens rather than after a client notices on their own?

[fill in]

### Q8

The pipeline is sized off today's average and peak-hour rate: what is your story for a one-time coordinated re-scrape or a sales-driven spike that doubles gold-tier client count in a month, does the design degrade gracefully or does it fall over, and what is the first thing that breaks?

[fill in]
