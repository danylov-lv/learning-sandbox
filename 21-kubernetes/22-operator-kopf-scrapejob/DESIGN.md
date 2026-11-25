# Design Review -- ScrapeJob Operator

Fill in each section grounded in the operator you actually wrote in
`src/operator.py` and what CP1/CP2 actually observed against it -- not
generic controller-pattern prose copied from somewhere else. This is
graded (`tests/validate_cp3.py`): every section needs real content past
the shipped `[fill in` marker, a minimum length, and at least two mentions
of concepts specific to this operator (a finalizer, the `scrapejob-name`
label, idempotency) rather than only abstract Kubernetes vocabulary.

## The reconcile loop, in your own words

[fill in -- trace exactly what happens, mechanically, from `kubectl apply`
of a `ScrapeJob` to a running worker Pod: what kopf watches, what your
`on_create` handler actually calls, and what object ends up owning what.
Then trace what happens on `kubectl patch --replicas`: which handler
fires, and what it changes versus what it leaves alone.]

## Level-triggered vs. edge-triggered

[fill in -- explain the difference in your own words, then answer
concretely for YOUR `on_update`: if your operator missed an update event
entirely (crashed and restarted between the patch and the next
reconcile), would the ScrapeJob's worker pool still end up correct once
your operator came back up? Why or why not, given what your handler
actually reads and writes?]

## Owner references and garbage collection

[fill in -- what does `kopf.adopt` actually set on the child Deployment,
and what would Kubernetes do with it if your `on_delete` handler didn't
exist at all? Given that GC would eventually clean up the child anyway,
why does this task still require an explicit `on_delete` -- what does
CP2's bounded wait for the Deployment's disappearance depend on that pure
owner-reference GC doesn't guarantee?]

## Idempotency of reconcile

[fill in -- kopf re-delivers `on_create` if your operator restarts before
marking the handler's success, and re-runs handlers on retries after a
transient failure. Walk through what YOUR `on_create` does if it's
invoked a second time for a `ScrapeJob` whose Deployment already exists --
does it error, silently do nothing useful, or actually reconcile? If you
didn't handle this, say so and explain what would actually happen.]

## Where this would break in production

[fill in -- name at least three concrete gaps between this toy operator
and a production-grade one: what happens if you run two copies of this
operator process at once (no leader election here) and both react to the
same event; what a real operator reports on `status.conditions` that
yours never writes at all; and one more gap of your choosing (RBAC scope,
rate limiting/backoff on repeated failures, multi-cluster, testing
strategy, whatever you actually noticed while building this).]
