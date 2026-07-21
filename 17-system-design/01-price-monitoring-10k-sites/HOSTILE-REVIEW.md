# Hostile review questions

These are the questions a skeptical staff engineer asks in the design
review for this system. Answer each one as `### Q1` .. `### Q8` under the
`## Hostile review responses` section of `DESIGN.md`. Restating the
question is not an answer — the validator rejects a verbatim copy.

**Q1.** A target site changes its markup. The fetch still returns `200
OK` with a normal-looking response size, so nothing in your retry or
health-check logic sees a failure — but the parser's price selector no
longer matches, and every extraction for that site silently returns
null or zero from now on. How does your system detect this class of
failure, which never shows up as a fetch error, a timeout, or a non-200
status?

**Q2.** Your hot tier refreshes every 15 minutes. If every hot-tier URL
is scheduled on the same wall-clock grid (`:00`, `:15`, `:30`, `:45`),
what actually happens to your fleet, your proxy pool, and the target
sites' rate limits at each of those boundaries? Walk through the
mechanism that prevents this, concretely — not "we add jitter" as a
slogan, but where the jitter is applied and what bounds it.

**Q3.** You've defined a freshness SLO. Explain exactly what event you
timestamp, what "stale" means as a threshold on that timestamp, and then
describe how you would prove, from production telemetry alone, that the
SLO was met (or missed) for a given tier over the past 24 hours — without
re-deriving the capacity model from scratch to reconstruct what should
have happened.

**Q4.** Your proxy pool doesn't fail outright — it degrades. Egress
starts taking 3-4x longer per request and your success rate on first
attempt quietly drops. Nothing pages anyone because nothing is down.
What is the first component in your architecture to fall over, and how
does the rest of the system behave in the minutes after that — does it
degrade gracefully or cascade?

**Q5.** Your capacity model treats the URL set as a uniform pool split
into three tiers by fixed fractions. In reality, site-to-site URL counts
are Zipf-distributed — a handful of large catalog sites contribute a
wildly disproportionate share of the URLs in any given tier. What
actually happens to a single oversized site's freshness and to your
per-site politeness budget when it alone accounts for, say, 4-5% of the
entire hot tier?

**Q6.** Your retry math assumes each attempt is an independent trial
with a fixed success probability. But a real failure mode is a site
IP-banning your egress range specifically — every subsequent attempt
against that site from that proxy is now correlated, not independent,
and retrying just burns egress for a certain failure. How would your
system tell "this is a transient, independent failure, retry as
planned" apart from "this proxy/site pair is burned, stop retrying and
do something else," and what does it do differently in the second case?

**Q7.** You poll every URL at a fixed cadence per tier regardless of how
often its price actually changes. Quantify the two failure directions
this causes: a cold-tier URL that has a flash sale and changes price
five times in an hour (what does your system report as "the price" for
that hour?), and a hot-tier URL whose price never changes for weeks
(what did those extra fetches buy you)? Would a fixed cadence per tier
survive contact with real price-change frequency data, or does the
design need something adaptive?

**Q8.** A downstream team says your freshness numbers "don't add up" for
a specific day last week — they claim prices they pulled were staler
than the SLO promises. Without access to you, walk through what
dashboards, logs, or stored metrics would need to already exist for
someone on-call to reconstruct exactly what the fleet was doing that
day, tier by tier, and confirm or refute the claim.
