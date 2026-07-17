# k8s-bonus — Running the Spider Pool on Your Own Chart

Optional. Zero capstone weight — skip it freely; nothing else in this
module depends on it. It exists because "add another spider" is a one-line
`docker compose up --scale` in this module's stack, and a `kubectl scale`
one-liner on a shared cluster — but the chart behind that one-liner is
almost always someone else's. This bonus makes you write it yourself.

## Backstory

At work you deploy spiders through infrastructure someone else authored: a
platform team's Helm chart you fill a `values.yaml` into, or an Argo/Flux
template you never open. You set `replicaCount` and move on. You have never
had to defend the Deployment, HPA, and PodDisruptionBudget underneath —
where the pod labels are defined, why the HPA's `scaleTargetRef` has to
match the Deployment's name byte for byte, what happens to in-flight crawl
work when a node drain evicts a worker the PDB was supposed to protect.

Here you write that chart from scratch — no `helm create` scaffold, every
template one you can explain — for this module's own spider worker: the
instrumented crawler from task 06 that already exposes `/metrics`. You give
it a Deployment with a configurable replica count, an HPA that can move that
count under load, a PodDisruptionBudget so voluntary disruptions don't take
out the whole pool at once, and resource requests/limits you derived from
watching the spider actually run.

## What's given

- `chart/` — a chart skeleton written from scratch:
  - `Chart.yaml` — filled (`name: spider-platform`, apiVersion v2, a
    version).
  - `values.yaml` — filled with sane defaults (image, `spider.replicaCount`,
    `resources`, `autoscaling` on/off + min/max/targetCPU, `pdb.minAvailable`,
    liveness/readiness `probes`). These are the knobs; your templates
    consume them. The `resources` defaults are deliberately placeholder
    guesses you are meant to replace with measurements — and deliberately
    NOT the copy-paste `100m/128Mi` the validator warns about.
  - `templates/` — EMPTY placeholder files (`deployment.yaml`, `hpa.yaml`,
    `pdb.yaml`, `_helpers.tpl`, each just a TODO comment). These are what you
    write. On the shipped skeleton the chart renders nothing, so the
    validator fails until you fill them.
- `tests/validate.py` — offline-first validator (renders and lints the
  chart; needs only `helm` on PATH). A live section runs only if a kind/k3d
  cluster is reachable and skips itself with a notice otherwise.
- `hints/` — three escalating hints. `NOTES.md` — your write-up template.

## What's required

Write the templates in `chart/templates/` so the chart renders and lints:

1. **A spider worker Deployment.** `replicas` from
   `.Values.spider.replicaCount`; one consistent pod label set defined once
   (a `_helpers.tpl` label helper is the clean way) and reused by the HPA and
   PDB below; a container running your spider image, wired to the target site
   (`spider.targetBaseUrl`) and exposing the `/metrics` port; both a
   **livenessProbe** and a **readinessProbe**; and a `resources` block that
   sets `requests` **and** `limits` for both cpu and memory.
2. **A HorizontalPodAutoscaler** (`autoscaling/v2`) whose `scaleTargetRef`
   names that Deployment (`apps/v1`, `kind: Deployment`, exact name), with
   `minReplicas`/`maxReplicas` from values and at least one metric (CPU
   utilization is fine here — see the note in `values.yaml` on why crawl
   *queue depth* is the metric a real spider pool would scale on, and why
   this chart stays on core-k8s CPU instead).
3. **A PodDisruptionBudget** whose `spec.selector.matchLabels` matches the
   Deployment's pod labels exactly and sets `minAvailable` or
   `maxUnavailable` from values.
4. **Derive resources from measurement.** Run the spider, watch it
   (`kubectl top pod` with metrics-server, or `docker stats` against the
   container) across a few crawl cycles under load, and set the requests/
   limits from what you saw — recording the raw numbers as comments in
   `values.yaml` next to the values they justify. Copy-pasted `100m/128Mi`
   is specifically checked for and called out.
5. **Fill in `NOTES.md`** — the measurement table, the HPA/PDB choices, and
   (if you did the live stretch) what you observed scaling the pool.

## Running it

Offline (always run, no cluster needed), from the module root:

```bash
uv run python k8s-bonus/tests/validate.py
```

`helm lint` should also be clean:

```bash
helm lint k8s-bonus/chart
```

### Optional live stretch (not required by the validator)

Actually deploying to a local **kind/k3d** cluster is a stretch goal — the
validator only renders the chart with `helm template` + `helm lint` and does
not need a cluster. If you want to run it for real:

```bash
# from 13-scraping-at-scale/, with `docker compose up -d` and generate.py done
docker build -t spider-platform:dev -f k8s-bonus/docker/Dockerfile .   # your own Dockerfile
kind load docker-image spider-platform:dev
helm install spider-platform k8s-bonus/chart \
  --set image.repository=spider-platform --set image.tag=dev
kubectl scale deployment spider-platform --replicas=4
kubectl get pods -w      # watch workers join the pool
```

Reaching the host-side target site (`:8313`) and the `/metrics` scrape from
inside kind is the same "reach the host from a pod" problem module 06's
k8s-bonus covered — `host.docker.internal` or kind `extraPortMappings`.

## Completion criteria

```bash
uv run python k8s-bonus/tests/validate.py
```

PASSED requires (offline, always run): the chart renders via `helm template`
and passes `helm lint`; the rendered output contains a Deployment whose
container sets both requests and limits (cpu and memory; a warning — not a
failure — if they equal the classic copy-paste defaults) and defines both a
liveness and a readiness probe, a HorizontalPodAutoscaler (`autoscaling/v2`)
whose `scaleTargetRef` names that Deployment and which has `minReplicas`,
`maxReplicas`, and at least one metric, and a PodDisruptionBudget whose
selector matches the Deployment's pod labels and sets `minAvailable` or
`maxUnavailable`. The live section (kind/k3d cluster reachable) additionally
reports whether the release is installed; when no cluster is reachable it
prints a notice and skips, it does not fail.

## Estimated evenings

1

## Topics to read up on

- HorizontalPodAutoscaler v2: the `metrics` array shape, `Resource` vs
  `Pods`/`External` metric types, and why CPU is a weak proxy for a spider
  pool's real bottleneck (crawl-queue depth / pending-URL backlog)
- Scaling on a custom metric — prometheus-adapter exposing the `queue_depth`
  gauge from task 06, or KEDA — as the production-grade alternative to a
  CPU-based HPA for this workload. Read about it, don't build it; it's a
  separate adapter/CRD outside this chart's scope
- PodDisruptionBudgets on a multi-replica Deployment: how `minAvailable`
  interacts with a rolling update or a node drain, and what happens to
  in-flight crawl work when a protected pod gets evicted anyway
- Liveness vs. readiness probes: what each one gates, and why `/metrics` is a
  workable (if crude) liveness signal for a worker that has no real HTTP
  surface
- Helm templating basics: `_helpers.tpl` named templates for a single shared
  label set, `.Values` plumbing, and `include`/`nindent`
- Requests vs. limits and QoS classes — apply the same ground module 06's
  bonus covered to this differently-shaped workload
- Reaching host services from inside kind (`host.docker.internal`, kind
  `extraPortMappings`) and loading a locally built image
  (`kind load docker-image`) vs. pushing to a registry

## Off-limits

`.authoring/design.md` (module root) holds the target app's full defense/
behavior contract and the corpus ground-truth values — spoilers for every
task in this module. This bonus doesn't need any of it: you are packaging a
spider you already built, not scraping. Don't read it to do this level.
