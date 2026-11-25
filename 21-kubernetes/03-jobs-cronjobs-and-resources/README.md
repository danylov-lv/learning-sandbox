# 03 — Jobs, CronJobs, and resources

## Backstory

The site you scrape changes shape every so often, and every time it does
the catalog you've already crawled goes stale in patches. Two different
operational needs come out of that, and they map to two different
Kubernetes objects, not one:

- Sometimes you need to re-scrape a known batch of already-identified
  shards *right now*, in parallel, and know for certain when every shard
  is done. That's a **Job**: a run-to-completion workload, not a
  long-running server — there is no "restart it forever," there is
  "run it until the required number of shards have succeeded, then stop."
- Sometimes you want a small routine re-scrape to happen automatically,
  on a schedule, without you kicking it off by hand every time, and you
  want to be a little defensive about it — no back-to-back overlapping
  runs, a bounded number of old run records kept around instead of an
  unbounded pile. That's a **CronJob**: a template for spawning a Job,
  on a schedule, with policy around what happens if a previous run is
  still going when the next one is due.

Both workloads process the same conceptual thing: a "shard" of the
catalog. In this task the shard-processing pod doesn't do a real scrape —
it simulates one: sleep a few seconds (as if doing network I/O), print
that the shard is done, exit 0. You write the actual command; the image
already has `python3` on it (`sandbox20-app:1.0`), so `python3 -c "..."`
is enough — no new image, no Dockerfile changes.

Neither workload gets to run on the cluster unconstrained: both container
specs need real CPU/memory requests **and** limits, and the specific
numbers you're given below land you in a specific Kubernetes QoS class —
which one, and why, is part of what this task is testing.

## What's given

`src/` contains two stub files, `job.yaml` and `cronjob.yaml`, each with a
`# TODO(you): ...` comment block describing the shape expected (see
"What's required" below for the full contract) and no working object.
`kubectl apply -f src/job.yaml` (or `cronjob.yaml`) against the stubs
applies nothing — that's expected until you fill them in.

## What's required

### `src/job.yaml` — Job `rescrape`

- `metadata.name: rescrape`.
- The shard workload: each pod runs a command that sleeps a few seconds,
  prints something indicating the shard is done, then exits `0`.
  `image: sandbox20-app:1.0`, `imagePullPolicy: IfNotPresent` (same
  registry caveat as task 01 — this image only exists inside kind's
  containerd).
- `spec.completions: 4` — four shards need to run to completion in total.
- `spec.parallelism: 2` — at most two shard pods running at once.
- `spec.backoffLimit: 2` — give up on the Job after 2 pod failures, not
  the default 6.
- `spec.template.spec.restartPolicy: Never` — read the hints if you
  reach for `Always` here and something rejects your manifest.
- The container has **both** of these set, not just one:
  - `resources.requests`: `cpu: 50m`, `memory: 64Mi`
  - `resources.limits`: `cpu: 200m`, `memory: 128Mi`

### `src/cronjob.yaml` — CronJob `scheduled-scrape`

- `metadata.name: scheduled-scrape`.
- `spec.schedule: "* * * * *"` — every minute (this is a lab, not
  production; a real routine re-scrape would run far less often).
- `spec.concurrencyPolicy: Forbid` — if a previous run's Job is still
  active when the next tick fires, skip that tick rather than starting a
  second overlapping run.
- `spec.successfulJobsHistoryLimit: 2`, `spec.failedJobsHistoryLimit: 1`
  — bound how many completed/failed Job objects the CronJob controller
  keeps around instead of letting them accumulate forever.
- `spec.startingDeadlineSeconds` — set to some reasonable positive value
  of your choice (think about what this field actually protects against
  before picking a number — see the hints if you're not sure).
- `spec.jobTemplate.spec` — the same shard workload as the Job above
  (same image, same command shape, same resources), but `completions: 1`
  this time (a scheduled run processes one shard per tick, not four) and
  the same `restartPolicy: Never`.

## Completion criteria

From this task directory:

```bash
uv run python tests/validate.py
```

The validator (namespace `t03`, recreated fresh, deleted at the end
whether you pass or fail):

1. Applies `src/job.yaml`, waits for the Job to reach `status.succeeded ==
   4` (bounded timeout), and checks the Job's own spec fields
   (`completions`, `parallelism`, `backoffLimit`, `restartPolicy`) match
   the contract above.
2. Looks at the four finished pods' own `status.startTime` and
   termination timestamps and asserts that **at least two of them
   actually ran at the same time** — proof that `parallelism: 2` did
   something, not just that the field is set to the right number on
   paper. If your workload finishes near-instantly you may not get
   overlap by chance; a few seconds of sleep per shard gives the
   scheduler enough of a window.
3. Asserts every job pod's container has requests and limits **exactly**
   as contracted, and that the pod's own `status.qosClass` is what those
   numbers actually produce (not `Guaranteed`, not `BestEffort`).
4. Applies `src/cronjob.yaml` and checks the structural fields:
   `schedule`, `concurrencyPolicy`, both history limits,
   `startingDeadlineSeconds` present, `jobTemplate` restartPolicy and
   resources.
5. Waits (bounded) for the CronJob to spawn its first Job and for that
   Job to complete, then patches the CronJob to `suspend: true` (so it
   stops firing) and re-checks the history-limit fields are still what
   you set. It does **not** wait multiple minutes for old Job objects to
   actually get pruned down to those limits — that's a slower background
   process this task isn't grading.

## Estimated evenings

1

## Topics to read up on

- Job semantics vs. Deployment semantics — run-to-completion vs.
  keep-N-replicas-running-forever, and why a Job's pod template can't use
  `restartPolicy: Always`.
- `completions` vs. `parallelism` on a Job, and what `backoffLimit`
  actually counts (pod failures, at the Job level — not retries of one
  specific pod).
- Kubernetes QoS classes (`Guaranteed`, `Burstable`, `BestEffort`) — what
  combination of requests/limits across a pod's containers produces each
  one, and why it matters for eviction order under node pressure.
- CronJob `schedule` (standard cron syntax), `concurrencyPolicy`
  (`Allow`/`Forbid`/`Replace`), `successfulJobsHistoryLimit` /
  `failedJobsHistoryLimit`, and `startingDeadlineSeconds`.
