# Design review — price intelligence platform

Fill in every section below with your own writing. `tests/validate_cp1.py`,
`tests/validate_cp2.py` and `tests/validate_cp3.py` each check a subset of
these `## ` sections structurally: the heading exists, the body clears a
minimum length, it mentions the concrete mechanisms this design is about
(not just abstractions), it makes quantitative claims (numbers, rates,
sizes, percentages — not just prose), and no `[fill in` placeholder
survives. See `README.md` for exactly which sections belong to which
checkpoint.

## Problem statement and scope

[fill in: what this platform is, in a few sentences, and just as
important — what it explicitly does NOT do. Every design review starts by
someone asking "wait, is X even in scope?"]

## Requirements, SLIs and SLOs

[fill in: functional requirements, then a table or list of SLIs with
numeric SLO targets that a client contract could reference directly —
freshness, availability, delivery latency, data quality. Say who measures
each one and how.]

## Workload characterization

[fill in: describe the shape of the load in `workload.json` — tier skew
across hot/warm/cold, client-tier skew, tenant concentration, and where
the awkward parts of this workload are (the parts that make a naive
uniform design wrong).]

## Capacity model

[fill in: walk through what `src/estimate.py` computes and why. Fleet
size, egress, storage footprint, peak headroom — connect each number back
to a decision it drives.]

## Cost model

[fill in: the cost breakdown by component from `monthly_cost_by_component`,
which component dominates and why, and what would move the needle most if
you needed to cut cost.]

## Architecture

[fill in: the system's major pieces (acquisition, quality/contract layer,
historical storage, analytical serving, delivery, multi-tenancy control
plane, observability) and how they connect. A diagram described in words
is fine — this is graded on content, not on whether you can draw boxes.]

## Component responsibilities

[fill in: for each major component, what it owns — and just as
importantly, what it explicitly does NOT own. Overlapping ownership is
where outages start.]

## Data flow and contracts

[fill in: trace one price fact from a hostile site to a client's
delivered record. At each handoff, name the contract that guards it —
schema, validation rule, versioning scheme — and what happens when a
handoff violates its contract.]

## Storage and serving layout

[fill in: how the hot and cold tiers are actually laid out — partitioning
scheme, indexing, file/table format, compression — and what serves the
analytical query volume from `workload.json` without falling over.]

## Multi-tenancy and isolation

[fill in: how tenants share the fleet without sharing each other's data,
quota, or blast radius. Name the isolation mechanism (schema-per-tenant,
row-level security, per-tenant queues, quotas, etc.) and what a noisy
tenant cannot do to their neighbors.]

## Failure modes and blast radius

[fill in: for each major component, what happens when it fails, who
notices, and who is affected. Be specific about blast radius — "one
tenant" is a different answer than "everyone."]

## Degradation ladder

[fill in: under overload, what gets shed first, what second, what third —
and what is never shed no matter how bad things get. Tie this back to the
`utilization_at_peak` number from your capacity model.]

## Evolution at 10x

[fill in: what changes structurally at 10x the current volume — not "add
more machines" but what actually breaks in the current design and what
replaces it. Use `fleet_size_at_10x` and `storage_and_cost_at_10x` as your
starting point, then go beyond the arithmetic.]

## Hostile review responses

Answer each question from `HOSTILE-REVIEW.md` on its own merits — ground
your answer in the specific numbers and components of this design, not in
generic platitudes. A restated question or a one-line answer does not
count as answered.

### Q1

Which single component's failure would take the most revenue down with
it, and why is that an acceptable risk to carry?

[fill in]

### Q2

What does the system do on the day the single biggest target site blocks
your entire proxy pool at once?

[fill in]

### Q3

Where is the cost model most likely wrong by an order of magnitude, and
what would you measure in production to find out before the invoice
arrives?

[fill in]

### Q4

If the budget were cut in half tomorrow, what would you cut first, and
what would that cost you in capability?

[fill in]

### Q5

Which of your SLOs, as specified, cannot actually be measured with the
telemetry this design produces?

[fill in]

### Q6

What breaks at 10x load that does not break at 2x?

[fill in]

### Q7

If the freshness requirement tightened by 10x instead of the volume
growing 10x, what would you build differently?

[fill in]

### Q8

Which tenant behavior would degrade every other tenant first, and what
specifically stops it from doing so?

[fill in]

### Q9

What is the most likely way a data-quality regression reaches a client
silently, and how would you catch it before they do?

[fill in]

### Q10

If the dominant analytical query pattern changed overnight, what would
have to change in your storage layout, and how long would that migration
realistically take?

[fill in]

### Q11

Which failure mode in this design would breach a client's SLA before your
own alerting fires?

[fill in]

### Q12

If you had to defend this design's cost to a CFO in one paragraph, what
would you leave out of that paragraph, and could that omission come back
to bite you?

[fill in]

## Risk register

[fill in: a list of concrete risks specific to THIS design (not generic
"the server could crash" risks) — for each, what would catch it in
production, and what you would do about it. A table is fine: risk /
likelihood / impact / detection / mitigation.]
