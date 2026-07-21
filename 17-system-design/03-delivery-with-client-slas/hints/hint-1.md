# Hint 1

You've run producer/consumer spiders over RabbitMQ for two years, so the
mechanics of a queue feeding workers are not the hard part here. The hard
part is that this queue now has three tenants with contractually different
consequences for lateness, and a single shared crawl/delivery budget that
cannot always satisfy all of them at once.

Start from the commercial side, not the architecture side. Before drawing
any boxes, write down: what does each tier's contract actually promise
(SLI, SLO, SLA — these are three different things, look up the
distinction), what does "available" mean well enough that a client and you
would compute the same number from the same delivery log, and what
specifically happens — in dollars, not vibes — when a promise is missed.
Only once that's pinned down does it make sense to design the scheduler
that has to honor it.

Also sit with the difference between "the data is stale" and "the delivery
is late." They are not the same failure, they are not caught by the same
monitor, and they should not be priced the same way.
