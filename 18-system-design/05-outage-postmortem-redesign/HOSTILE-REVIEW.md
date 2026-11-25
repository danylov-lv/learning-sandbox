# Hostile review — 05 outage-postmortem-redesign

Eight questions a skeptical colleague would ask after reading your
`DESIGN.md`. Answer all eight inside `DESIGN.md`'s `## Hostile Review`
section, under the matching `### Q1`–`### Q8` heading — not in this file.
A restated question or a one-line non-answer does not pass; each answer
needs to actually engage with this specific incident's numbers and
evidence, not restate general system-design advice.

### Q1

The autoscaler scaled `scrape-worker` from 11 to 20 replicas at 09:35
in direct response to rising queue depth. Why did that action make the
incident worse rather than better, and what signal should the autoscaler
have been watching instead of queue depth?

### Q2

Would a circuit breaker around outbound requests to
`sunrise-outdoor.example` have helped here, or would it have merely
relocated the failure to a different part of the system? Be specific
about what a circuit breaker does and does not protect against in this
particular chain of events.

### Q3

`delivery-api` has no scraping logic of its own — it doesn't fetch
pages, parse HTML, or touch the retry queue. Why did it go down anyway,
and what boundary was actually missing between it and the
`scrape-worker` fleet? Name the specific mechanism, not just "isolation."

### Q4

Of the fixes in your "Redesign" section, which ones would have actually
shortened *this specific* 4-hour incident had they already been in
place, versus which ones would only prevent a *repeat* of the same class
of failure? These are not the same list — defend the distinction.

### Q5

Forget the full timeline you now have. At 09:40 — armed with only what
was on-screen at that moment (queue depth climbing, workers just scaled
11→20, `delivery-api` just started erroring, nobody yet knows the pool
is shared) — what would you have actually done, and would it have
worked?

### Q6

`retry-policy.yaml` shows `backoff.strategy: exponential, factor: 2`.
Someone reviewing that file in isolation, without doing the arithmetic,
could reasonably conclude backoff was already handled. Why would they be
wrong, and what would make this specific class of misconfiguration
impossible to ship again (not just "add a test" — what test, checking
what property)?

### Q7

The incident was only bounded by a human pausing consumers and manually
draining/redirecting the backlog at 11:10. What in your redesign makes
that manual step unnecessary the next time this class of failure starts,
and what is the automatic equivalent — with a concrete trigger
condition, not "detect the problem and react"?

### Q8

Your redesign presumably costs something: more infrastructure, more
operational complexity, or slower steady-state throughput. Argue that
the trade-off is worth it, and identify the smallest version of the
redesign that still closes the specific gap this incident exposed —
what's the first thing you'd cut if you had half the budget?
