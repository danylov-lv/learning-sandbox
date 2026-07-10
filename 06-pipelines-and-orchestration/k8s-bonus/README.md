# k8s-bonus — The Loader Leaves the Compose File

Optional. Zero capstone weight — skip it freely; nothing else in this
module depends on it. It exists because you deploy to k8s daily through
charts someone else wrote, and this module's loader is a small, real
workload that fits in one evening of writing a chart yourself.

## Backstory

The compose stack was always a sandbox. The platform team wants the daily
load running on the shared cluster like everything else: a chart in the
repo, a CronJob for the load, and — because "the pipeline is silently
dead" is the failure mode everyone fears most — a small always-on monitor
that watches `ops.load_audit` freshness. They will not accept a chart
whose resource requests were invented. Measured numbers or it doesn't
merge.

## What's given

- `src/Dockerfile` — a TODO skeleton (python-slim + uv). You write the
  real one.
- `src/loader/loader.py` — a stub entrypoint. The logic is your t02/t09
  incremental-loader work, repackaged to run once per invocation (one
  day's load per CronJob fire) and exit.
- `src/monitor/monitor.py` — a stub for the pipeline-monitor: your code,
  either an alert-sink-style stdlib HTTP server exposing a freshness
  status, or a plain loop that checks `ops.load_audit` recency and logs.
  Small is correct here.
- `src/helm/price-pipeline/` — a chart skeleton written from scratch:
  `Chart.yaml`, a `values.yaml` full of TODOs, and an empty `templates/`
  directory. Deliberately no `helm create` boilerplate — every template
  you ship is one you wrote and can defend.
- `tests/validate.py` — offline-first validator (renders and lints the
  chart; needs `helm` on PATH); a live section runs only if a kind
  cluster is reachable and skips itself with a notice otherwise.

## What's required

1. **Containerize the loader.** Finish `src/Dockerfile`: python-slim
   base, dependencies via uv, your loader as the entrypoint. Build it and
   load it into your kind cluster.
2. **Write the chart from scratch.** In
   `src/helm/price-pipeline/templates/`:
   - a **CronJob** running the daily load against this module's warehouse
     (the Postgres from docker-compose, reachable from inside kind — how
     you bridge that is your call; see topics),
   - a **Deployment** for the pipeline-monitor (1+ replicas, always on),
   - a **PodDisruptionBudget** targeting the monitor Deployment.
3. **Derive resources from measurement.** Run the monitor, measure it
   (`kubectl top pod` with metrics-server, or `docker stats` against the
   container), set the Deployment's requests/limits from what you saw,
   and write the measured numbers into `values.yaml` as comments next to
   the values they justify. Copy-pasted `100m/128Mi` is specifically
   checked for and called out.
4. **Fill in `NOTES.md`** — the measurement table and what you'd change
   before calling this production-grade.

## Completion criteria

```bash
uv run python tests/validate.py
```

PASSED requires (offline, always run): the chart renders via
`helm template` and passes `helm lint`; the rendered output contains a
CronJob with a schedule, a Deployment with both requests and limits set
(a warning — not a failure — if they equal the classic copy-paste
defaults), and a PDB whose selector matches the monitor Deployment. The
live section (kind cluster reachable) additionally checks the release is
installed; when no cluster is reachable it prints a notice and skips,
it does not fail.

## Estimated evenings

1

## Topics to read up on

- Reaching a host service from inside kind: `host.docker.internal`,
  kind `extraPortMappings`, and when each applies
- Loading a locally built image into kind (`kind load docker-image`) vs.
  pushing to a registry
- CronJob semantics: `concurrencyPolicy`, `startingDeadlineSeconds`,
  `backoffLimit`, and what a missed schedule does
- Requests vs. limits: what each actually controls (scheduling vs.
  cgroup enforcement), QoS classes, and why limits==requests is a
  defensible starting point for a tiny steady-state service
- metrics-server and `kubectl top` in kind
- PodDisruptionBudgets: what they protect against (voluntary
  disruptions), and what `minAvailable: 1` means for a 1-replica
  Deployment during a node drain
- Helm chart anatomy without `helm create`: Chart.yaml apiVersion v2,
  values plumbing, `include`/`template` helpers you actually need vs.
  boilerplate you don't
- python-slim + uv in a Dockerfile: layer caching around `uv sync`,
  `--no-dev`, lockfile-driven installs
