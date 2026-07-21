# DESIGN: Multi-Tenant Platform

## Requirements and tenancy model

[fill in: who the tenants are (plan tiers, rough count, rough size
distribution), what each tenant expects (throughput, freshness, data
isolation, uptime), and what tenancy model you're building --
shared-everything, shared-nothing, or a hybrid where some layers are
pooled and others are dedicated per tier. Name the layers explicitly:
crawler fleet, queue, proxy pool, object storage, metadata/control plane.]

## Isolation boundaries

[fill in: for each shared layer named above, what is actually shared
between tenants and what is isolated, and why that split was chosen. Be
concrete about the mechanism -- namespace-per-tenant, schema-per-tenant,
row-level security with a `tenant_id` column, dedicated queue per tier,
dedicated proxy sub-pool per tier, etc. -- not just "isolated."]

## Quotas and admission control

[fill in: how a tenant's allowed rate/concurrency is enforced at the
edge, what happens when a new tenant tries to sign up and the platform is
near its admission-time overcommit ratio, and what the burst allowance
per tenant actually permits before it's throttled.]

## Fair-share scheduling

[fill in: describe, in your own words, how the platform splits a finite
crawl budget across tenants when total demand exceeds capacity --
reference the weighted max-min / progressive-filling rule from the
README, explain what "satisfied" and "unsatisfied" mean here, and give a
concrete example from `workload.json` of who gets squeezed and why.]

## Capacity model

[fill in: summarize what `src/estimate.py` says about this workload --
total demand vs. usable capacity, the overcommit ratio, which tenants are
unsatisfied under fair share, and the capacity that would be needed to
satisfy everyone at the target headroom.]

## Noisy-neighbour containment

[fill in: what stops one tenant's misbehaving crawl job (retry storm,
huge response bodies, a target site that starts redirecting into an
infinite loop) from degrading service for every other tenant on shared
infrastructure -- name the specific mechanisms: rate limiting, circuit
breakers, bulkheads, per-tenant connection pool caps, timeouts, backoff
ceilings.]

## Cost attribution and chargeback

[fill in: how infrastructure cost gets attributed back to each tenant
(reference the per-request, per-egress, per-storage cost model), whether
this is showback or chargeback, and what the margin looks like across the
tenant mix in `workload.json`.]

## Security and data boundary

[fill in: the hard boundary between one tenant's data and another's --
at rest, in transit, and in the control plane/dashboards -- and what
prevents cross-tenant data leakage or a tenant issuing a request that
targets another tenant's or the platform's own infrastructure.]

## Bottlenecks and failure modes

[fill in: where this design breaks first under load or under a partial
outage, and what the blast radius of each failure looks like -- does one
tenant's problem ever become every tenant's problem?]

## Evolution at 10x

[fill in: what changes when tenant count and demand both grow 10x -- what
in this design stops scaling linearly first, and what you'd change about
isolation, admission control, or the fair-share scheduling to cope.]

## Hostile Review

### Q1

What stops one tenant's target site from getting the shared proxy pool
banned for every other tenant sharing that pool?

[fill in]

### Q2

Can one tenant infer another tenant's target list -- which sites it
scrapes, how often -- purely from shared timing, cost, or capacity
signals?

[fill in]

### Q3

`requests/second` is the unit fair share optimizes, but one tenant's pages
are 40x heavier than another's. What does "fair" mean when the unit is
wrong?

[fill in]

### Q4

Who pays for a retry storm caused by a tenant's own broken selectors --
the tenant, the shared egress/proxy budget, or nobody until someone
notices?

[fill in]

### Q5

The biggest tenant doubles its demand and a smaller tenant is
contractually guaranteed a floor. Walk through what the fair-share
algorithm actually produces, and who gets squeezed.

[fill in]

### Q6

What in the isolation boundary stops (or contains) a tenant's request
that accidentally or intentionally targets another tenant's or the
platform's own infrastructure?

[fill in]

### Q7

Storage is billed at a flat per-GB rate for every tenant. What happens to
margin when a tenant's data compresses or dedupes far better or worse than
the platform-wide average that rate assumes?

[fill in]

### Q8

Two unsatisfied tenants escalate for different business reasons that the
fair-share formula cannot see. Where, if anywhere, does business priority
enter the system, and what do you give up if it does?

[fill in]
