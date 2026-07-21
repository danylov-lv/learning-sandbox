# Hostile review — questions for the panel

These are the questions a genuinely skeptical design-review panel would
ask about the price intelligence platform. They are not softballs. Answer
each one in `DESIGN.md`'s `## Hostile review responses` section, under
the matching `### Qn` heading — on its own merits, grounded in the
specific numbers and components of *this* design, not in generic
platform-engineering platitudes.

### Q1

Which single component's failure would take the most revenue down with
it, and why is that an acceptable risk to carry?

### Q2

What does the system do on the day the single biggest target site blocks
your entire proxy pool at once?

### Q3

Where is the cost model most likely wrong by an order of magnitude, and
what would you measure in production to find out before the invoice
arrives?

### Q4

If the budget were cut in half tomorrow, what would you cut first, and
what would that cost you in capability?

### Q5

Which of your SLOs, as specified, cannot actually be measured with the
telemetry this design produces?

### Q6

What breaks at 10x load that does not break at 2x?

### Q7

If the freshness requirement tightened by 10x instead of the volume
growing 10x, what would you build differently?

### Q8

Which tenant behavior would degrade every other tenant first, and what
specifically stops it from doing so?

### Q9

What is the most likely way a data-quality regression reaches a client
silently, and how would you catch it before they do?

### Q10

If the dominant analytical query pattern changed overnight, what would
have to change in your storage layout, and how long would that migration
realistically take?

### Q11

Which failure mode in this design would breach a client's SLA before your
own alerting fires?

### Q12

If you had to defend this design's cost to a CFO in one paragraph, what
would you leave out of that paragraph, and could that omission come back
to bite you?
