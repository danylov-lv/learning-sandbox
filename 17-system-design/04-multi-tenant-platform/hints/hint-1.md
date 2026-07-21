Start from the layers you already operate, not from the algorithm. You run
crawlers, a queue, and storage on Kubernetes today for one team. Go layer
by layer -- crawler fleet, queue, proxy pool, object storage, control
plane/dashboards -- and for each one ask the question you already ask
about pods and namespaces at work: is this thing one shared pool serving
everyone, or does each tenant get its own? Neither answer is free. A
shared pool is cheaper and simpler to operate but means one tenant's
behavior can affect another's. A dedicated pool per tenant is safe but
doesn't share economics the way the business model needs it to. Most real
platforms land somewhere in between, and where they land differs layer by
layer -- it's entirely normal for the proxy pool to be pooled-per-tier
while storage is isolated-per-tenant.

Once the isolation shape is settled, the "fair share" question stops being
abstract: it's "given a finite pool of something (crawl slots, proxy
bandwidth), how do multiple tenants with different contracts split it when
demand exceeds supply?" That's the scheduling half of the task. Don't
reach for the formula yet -- first decide, in prose, what "fair" should
mean for your tenant mix (equal split? proportional to what they pay?
proportional to some notion of promised throughput?). The README pins the
exact algorithm for the code; your design doc is where you justify why
that's the right notion of fairness for this business, and where you
notice its limits (the hostile-review questions are aimed squarely at
those limits).
