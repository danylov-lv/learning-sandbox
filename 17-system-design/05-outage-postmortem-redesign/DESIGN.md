# DESIGN — 05 outage-postmortem-redesign

## Incident summary

[fill in: a short, factual summary of the incident as you'd write it at
the top of a real postmortem — what broke, what customers experienced,
how long it lasted, how it was resolved. No analysis here, just the
shape of the event, oriented for someone who wasn't in the room.]

## Causal chain

[fill in: reconstruct the full causal chain from INCIDENT.md's evidence,
first anomaly to customer-facing impact to how it was actually stopped.
For each hop, state the mechanism — why did this step actually lead to
the next one, not just that it preceded it. Call out where the naive
first read of the evidence (what the on-call engineers believed at the
time) differs from what the full timeline actually shows.]

## Quantified analysis

[fill in: walk through what your src/estimate.py functions actually
produce for this workload, and what each number means for the incident.
Reference the specific figures — retry amplification, effective offered
load, queue growth rate, peak backlog, DB connections demanded vs. pool
size, drain time, error-budget burn. Connect each number back to a
specific moment or piece of evidence in INCIDENT.md.]

## Contributing factors

[fill in: the conditions that had to co-occur for this to become a
4-hour SEV1 rather than a contained, boring retry storm — the retry
policy's actual behavior, the shared resource, the autoscaling signal,
the alerting gaps, anything else you can point to directly in the
evidence.]

## Redesign

[fill in: the specific mechanism(s) you would put in place at each
layer that failed, sized against the same capacity model where that
makes sense (e.g. what pool size, what bulkhead split, what circuit
breaker threshold, what backoff policy actually prevents amplification
at this failure rate). Not a list of buzzwords — say what changes,
where, and why it closes the specific gap this incident exposed.]

## Blast radius and isolation

[fill in: what should the failure domain have been, and what let it
spread past that boundary? Be concrete about what shares what (pools,
queues, compute, deploy units) today, and what your redesign separates.]

## Detection and alerting

[fill in: what signal, if alerted on, would have caught this early —
and why didn't any of the signals that existed already catch it? Be
specific about which existing alert rule had the gap and what you'd
change about it, not just "add more alerts."]

## Verification plan

[fill in: how would you prove the redesign actually works, before
trusting it in production? Describe a concrete game-day / chaos drill —
what you'd inject, what you'd watch, what result would tell you the
fix holds and what result would tell you it doesn't.]

## Hostile Review

### Q1

Why did the autoscaler's scaling action make the incident worse rather
than better, and what signal should it have scaled on instead of queue
depth?

[fill in]

### Q2

Would a circuit breaker around outbound requests to
`sunrise-outdoor.example` have helped here, or would it have merely
relocated the failure to a different part of the system?

[fill in]

### Q3

`delivery-api` has no scraping logic of its own. Why did it go down
anyway, and what boundary was actually missing between it and the
`scrape-worker` fleet?

[fill in]

### Q4

Of the fixes in your "Redesign" section, which ones would have actually
shortened this specific incident, versus which ones would only prevent
a repeat of the same class of failure?

[fill in]

### Q5

At 09:40, armed with only the information actually available at that
moment, what would you have actually done, and would it have worked?

[fill in]

### Q6

`retry-policy.yaml` shows an exponential backoff configured. Why would
someone reviewing that file in isolation be wrong to conclude backoff
was already handled, and what would make this specific misconfiguration
impossible to ship again?

[fill in]

### Q7

The incident was only bounded by a human manually pausing consumers and
draining the backlog. What in your redesign makes that manual step
unnecessary next time, and what is the automatic equivalent?

[fill in]

### Q8

Your redesign presumably costs something. Argue the trade-off is worth
it, and identify the smallest version of the redesign that still closes
the specific gap this incident exposed.

[fill in]
