# Hostile Review

Eight questions a skeptical colleague (or an actual paying customer's
security team) would ask about this design. Answer them inside
`DESIGN.md`'s `## Hostile Review` section, under `### Q1` .. `### Q8` --
restate the question, then actually answer it. Do not answer them here;
this file is the question list only.

1. `acme_enterprise` is a large tenant whose target sites are unknown to
   you in advance. What stops one tenant's target site from getting the
   shared proxy pool banned (IP-blocked, rate-limited platform-wide) for
   every other tenant sharing that pool?

2. `borealis_pro` and a competitor of theirs, also a tenant on this
   platform, both scrape overlapping retail categories. Can `borealis_pro`
   infer anything about the competitor's target list -- which sites it
   scrapes, how often, how many pages -- purely from shared signals it can
   observe (queue depth, billing line items, proxy pool latency, shared
   dashboards)? What would have to leak for that inference to work, and
   what closes it off?

3. `requests/second` is the unit `fair_share_allocation` optimizes.
   `ember_starter`'s pages average 240 KB; `cirrus_pro`'s average 6 KB --
   40x lighter. Under equal weight, both get the same rps. Is that fair?
   What would "fair" even mean here, and does your platform charge or
   schedule on a unit that actually reflects the resource being contended
   for?

4. `delta_starter` ships a selector that breaks when the target site
   changes its markup, and now retries every failed request with
   exponential-ish backoff that isn't very exponential, hammering the same
   URL. Who pays for that traffic -- against the shared proxy egress
   budget, against `delta_starter`'s own quota, against nobody until
   someone notices? Walk through what actually happens in your design in
   the first five minutes of that retry storm.

5. `acme_enterprise` calls tomorrow and doubles its demanded rate.
   `borealis_pro`'s contract guarantees it a floor allocation that your
   original design didn't model. Trace through what your fair-share
   allocation actually produces in this scenario and who ends up
   squeezed -- then say plainly whether weighted max-min fairness as
   specified in this task can represent a contractual floor at all, or
   whether it needs to sit outside the algorithm.

6. A starter-tier tenant submits a target list that (by mistake or by
   intent) includes a URL that resolves to another tenant's staging
   environment, or to internal platform infrastructure. What in your
   isolation boundary would stop that request from ever being issued, or
   at minimum contain the blast radius once it is?

7. Your cost model bills storage at a flat per-GB rate for every tenant.
   One tenant's scraped payloads compress or dedupe far better than the
   platform-wide average this rate assumes; another's is far worse. What
   does that do to each tenant's margin, and is a flat per-GB rate still
   the right chargeback mechanism once tenants start comparing notes?

8. Two unsatisfied tenants from the same fair-share run both escalate.
   One is on a monthly contract and has said, in writing, that it will
   churn this week if throughput doesn't improve. The other has a larger
   contract, a slower sales cycle, and more patience. Weighted max-min
   fairness, as specified, cannot see either fact -- it only sees weight
   and demand. Where, if anywhere, does business priority like this enter
   your system, and what do you give up in the isolation/fairness story if
   it does?
