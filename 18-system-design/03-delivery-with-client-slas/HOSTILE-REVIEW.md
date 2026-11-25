# Hostile review — 03-delivery-with-client-slas

These are the questions a skeptical account manager, a client's procurement
lawyer, and your own on-call engineer would ask about this design, in that
order of increasing technical depth. Answer all eight, restated, under
`## Hostile Review` in `DESIGN.md` as `### Q1` .. `### Q8`. A restated
question with no answer below it does not pass.

**Q1.** Under the shared crawl budget, when there is not enough crawl
capacity to satisfy every tier's freshness deadline at once, who gets
starved — and how does your design make that an explicit, engineered
choice (a policy someone signed off on) rather than an emergent property of
whichever queue happens to drain first?

**Q2.** A record is delivered inside the freshness deadline, but the
underlying page it reflects was scraped three hours ago because the
upstream site was slow to change. Does that count against the freshness
SLA, the availability SLA, neither, or both — and why does that
distinction change which number moves on the penalty invoice?

**Q3.** A gold-tier client's ops team emails: "sixty of our deliveries
missed the 15-minute deadline last month," and disputes your invoice line
item. What evidence do you have — and specifically what evidence do they
not have — to settle the dispute per delivery, not per vibe?

**Q4.** A client's own webhook endpoint or SFTP drop goes down for six
hours. Walk through exactly what happens to your retry queue during those
six hours, and how you stop one client's downstream outage from consuming
crawl or delivery budget that the other tiers are contractually owed.

**Q5.** Is the error budget you track measured per client or per tier?
Name one concrete situation where aggregating to the tier level hides a
real problem — either one client dragging a tier's average into breach
while the rest are fine, or the reverse.

**Q6.** Your drain-after-outage math assumes the pipeline can run at its
full rated drain capacity while simultaneously serving live traffic. What,
concretely, throttles that in practice (a shared connection pool, a
rate-limited downstream API, a fixed delivery-worker fleet) — and what
happens to your recovery-time number if that assumption is off by 2x?

**Q7.** Bronze-tier clients silently absorb most of the backlog after an
incident because gold and silver get priority under the shared budget. Do
bronze clients know, in real time, that they have been deprioritized? What
has to be true commercially (contract language, a status page, a proactive
notice) before that deprioritization happens, not after a client notices on
their own?

**Q8.** The pipeline is sized off today's average and peak-hour rate. What
is your story for a one-time coordinated re-scrape (every client wants the
same historical backfill) or a sales-driven spike that doubles gold-tier
client count in a month — does the design degrade gracefully, or does it
fall over, and what is the first thing that breaks?
