The four layers from hint 1, narrowed to what to look at in each:

1. **The target site.** The synthetic monitor's alert rule only checks
   `status_code`. Look at what else changed in that same reading, and
   ask what a scraper's downstream parser would actually see if a site
   started doing this -- would it look like an error, or would it look
   like success with wrong content?

2. **The retry policy.** Read `retry-policy.yaml` as arithmetic, not as
   prose. `backoff.base_ms` and `backoff.factor` combine somehow to
   produce a delay before each requeue -- work out what delay that
   combination actually produces for attempt 2, 3, 4, 5. Separately,
   look at the worker log lines: notice *where inside the attempt* the
   exception happens relative to the DB step, and what that implies
   about whether a DB connection is already held when the exception
   fires.

3. **The autoscaler.** It scales on one specific metric. Ask two
   questions: does adding worker replicas fix the thing that's actually
   growing the queue (hint: compute what the fleet's total processing
   capacity is against what's actually arriving, attempts included, not
   just original messages) -- and separately, does adding worker
   replicas cost anything on a *different* resource that has nothing to
   do with queue depth?

4. **The shared infrastructure.** Two independent services are named in
   the evidence as touching `core-shared-pg`. One of them scrapes,
   the other doesn't. Find the exact chat line and alert that connect
   them, and ask what would have had to be true for one service's load
   to affect the other's ability to get a connection.

`workload.json` has a `baseline_worker_count` field alongside
`worker_count` -- that pairing is there so you can compare a "before"
and "after" of the same calculation, not just read one snapshot.
