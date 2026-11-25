# 05 — Chart dependencies, hooks, and diffing

## Backstory

The worker chart from task 04 does one thing: run the scrape worker. Now it
needs a queue in front of it -- a small Redis instance the worker consumes
from, seeded with a batch of work items the moment the release is first
installed. You could copy-paste a Redis Deployment/Service into your own
templates, but that's not how a real platform team would do it: they'd pull
in a small, focused Redis chart as a **dependency** and wire your worker to
it through values, not by hand-writing someone else's infrastructure. And
before "queue" workers were a thing, seeding initial data into that queue
at install time is exactly what Helm **hooks** are for -- a Job that runs at
a specific point in the release lifecycle, not just another workload.

Once your chart grows a dependency and a hook, `helm template` (which
renders your chart to plain YAML without touching a cluster) stops being
just a sanity check -- it becomes the fastest way to answer "what will
actually change if I flip this value?" before you ever run `helm upgrade`
against something real. This task ends with you doing that for real:
diffing a dev render against a prod render and writing down what you found
and why.

## What's given

- `given/queue-chart/` -- a small, complete Helm chart (not a stub, not
  something you edit): a single-replica `redis:7-alpine` Deployment and a
  ClusterIP Service, named via its own `queue-chart.fullname` named
  template. You'll add this as a dependency of your own chart; you never
  touch its internals. Worth reading once anyway -- notice its Service and
  Deployment are themselves annotated as `pre-install,pre-upgrade` hooks at
  a lower `hook-weight` than the hook Job you're about to write. That's not
  decoration: a `pre-install` hook runs before **any** normal release
  resource exists yet, including a dependency's own Service -- if redis
  weren't created earlier in the same hook phase, your seed-data hook would
  have nothing to connect to on a fresh install. Keep this in mind for the
  hook you write (see "What's required" step 2 and the gotcha called out
  there).
- `chart/` -- a chart skeleton: a `Chart.yaml` that's valid YAML with an
  empty `dependencies: []` list, and three `# TODO(you): ...` template
  stubs (`deployment.yaml`, `service.yaml`, `hook-job.yaml`). `values.yaml`
  is filled in already with the structure your templates should read from
  -- don't rename its top-level keys.
- `DIFF.md` -- an unfilled template for the diff-workflow write-up (step 3
  below).

## What's required

1. **Dependency.** Add `given/queue-chart` as a dependency in
   `chart/Chart.yaml`:
   ```yaml
   dependencies:
     - name: queue-chart
       version: "0.1.0"
       repository: "file://../given/queue-chart"
       condition: queue.enabled
   ```
   Then run `helm dependency build` from inside `chart/` -- this fetches
   the subchart into `chart/charts/queue-chart-0.1.0.tgz` (gitignored,
   don't hand-edit it). Write `chart/templates/deployment.yaml` and
   `service.yaml` so the worker:
   - Deployment is named `worker`, pod labels `app: worker`, replicas from
     `.Values.replicas`, image `{{ .Values.image.repository }}:{{
     .Values.image.tag }}`, `imagePullPolicy: IfNotPresent`, container port
     `8080`, `resources` from `.Values.resources`.
   - runs `WORK_MODE=consumer`, `QUEUE_BACKEND=redis` (literals),
     `REDIS_HOST` set to the queue-chart dependency's Service name --
     call its named template directly: `{{ include "queue-chart.fullname"
     . }}` (Helm shares its named-template namespace between a parent
     chart and every subchart it pulls in, so you can call a subchart's
     `_helpers.tpl` templates straight from your own templates), `REDIS_PORT=6379`
     (literal, matches the subchart), and `QUEUE_KEY` from `.Values.queue.key`
     (values-driven -- don't hardcode the string twice).
   - Service is named `worker`, ClusterIP, `port: 80` -> `targetPort: 8080`.

   **Gotcha:** a dependency's `condition:` gates its *entire* subchart when
   it's rendered -- including named templates it defines. Render with
   `--set queue.enabled=false` and `include "queue-chart.fullname" .` will
   error with "no template associated with template", because that template
   simply isn't loaded when the subchart is off. Wrap the
   `REDIS_HOST`/`REDIS_PORT`/`QUEUE_KEY` env entries (and anything else that
   calls into the subchart) in `{{- if .Values.queue.enabled }} ... {{- end
   }}` so the rest of your chart still renders cleanly with the dependency
   disabled.

2. **Hook.** Write `chart/templates/hook-job.yaml`: a Job named
   `queue-init` that seeds `.Values.queue.seedCount` items into the redis
   list named `.Values.queue.key`, using `REDIS_HOST`/`REDIS_PORT` wired the
   same way as the worker's. Use the image's own `python3` + the `redis`
   package already installed in it (see `app/Dockerfile`) -- a `command:
   [python3, -c, "..."]` one-liner (or short script) is enough. Annotate it:
   ```yaml
   annotations:
     "helm.sh/hook": pre-install,pre-upgrade
     "helm.sh/hook-weight": "-5"          # any integer; must run after redis's own hook
     "helm.sh/hook-delete-policy": before-hook-creation,hook-succeeded
   ```
   Same guard as step 1 applies here too: if `.Values.queue.enabled` is
   false there's nothing to seed and nothing to connect to, so wrap the
   whole Job in `{{- if .Values.queue.enabled }} ... {{- end }}`.
   Your seed script won't be the very first thing the cluster schedules
   after `helm install` -- give it a short connect-retry loop (a handful of
   seconds is plenty) rather than assuming redis answers on the first try.

3. **Diff workflow.** Create `chart/values-dev.yaml` and
   `chart/values-prod.yaml` -- two values overlays that differ in at least
   three concrete fields: `replicas`, the `resources` block
   (requests/limits), and `queue.key` (so dev and prod never share a queue).
   Then, for real, run something like:
   ```bash
   cd chart
   helm template t05-stack . -f values.yaml -f values-dev.yaml  > /tmp/dev.out
   helm template t05-stack . -f values.yaml -f values-prod.yaml > /tmp/prod.out
   diff /tmp/dev.out /tmp/prod.out
   ```
   and fill in `DIFF.md` (`## Command`, `## Differences found`, `## Why
   each difference exists`) with what you actually saw and why each
   difference makes sense for a dev vs. a prod environment. Write this from
   the real `diff` output, not from what you expect it to say.

## Completion criteria

From this task directory:

```bash
uv run python tests/validate.py
```

The validator, roughly in order:

- confirms `chart/Chart.yaml` declares the `queue-chart` dependency with
  `condition: queue.enabled` (this is the first thing checked -- the
  unmodified stub fails here);
- runs `helm dependency build` and expects it to succeed;
- runs `helm template` with default values and asserts a queue-chart-backed
  resource (redis) is present; runs it again with `--set
  queue.enabled=false` and asserts none are;
- checks the rendered `queue-init` Job's `helm.sh/hook`,
  `helm.sh/hook-weight`, and `helm.sh/hook-delete-policy` annotations;
- checks `chart/values-dev.yaml` / `values-prod.yaml` exist and actually
  render differently, and grades `DIFF.md` (required sections present,
  non-trivial length, mentions `helm template` and at least 3 concrete
  differing fields, no unfilled `[fill in` markers);
- installs the chart live into namespace `t05` and asserts: the `queue-init`
  hook Job completed strictly before the worker Deployment's pod was even
  created (not just before it became Ready -- before it existed at all);
  the redis pod and the worker pod both reach Ready; through a port-forward
  to the worker Service, `/metrics` eventually shows `app_processed_total >
  0` and `app_queue_depth == 0` -- proof the hook's seeded items actually
  got consumed by the running app, not just that the pods came up;
- uninstalls the release and asserts the `queue-init` Job is gone (its
  delete policy), then deletes the namespace.

## Estimated evenings

1-2

## Topics to read up on

- Helm chart dependencies: `Chart.yaml`'s `dependencies:` block,
  `repository: file://...` for a local sibling chart, `condition:` for
  gating a subchart on a parent value, and what `helm dependency build`
  actually does (vs. `helm dependency update`).
- Helm's named-template namespace being shared across a parent chart and
  its subcharts -- and the flip side: a `condition`-disabled subchart's
  named templates become unavailable too, not just its resources.
- Helm hooks: the hook phases (`pre-install`, `post-install`,
  `pre-upgrade`, ...), `helm.sh/hook-weight` for ordering hooks within the
  same phase, and `helm.sh/hook-delete-policy` (`before-hook-creation`,
  `hook-succeeded`, `hook-failed`) -- and the fact that a resource carrying
  hook annotations is tracked entirely separately from your chart's normal
  release manifest (which is why `helm uninstall` behaves differently for
  hook resources than for everything else).
- `helm template -f a.yaml > a.out` / `-f b.yaml > b.out` / `diff a.out
  b.out` as a debugging habit -- answering "what would actually change"
  before running `helm upgrade` against a real cluster.
