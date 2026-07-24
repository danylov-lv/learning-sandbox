# 07 -- Arc 2 Capstone: Package the Spider Platform

## Backstory

Every task in Arc 2 taught you one Helm skill in isolation: promoting
manifests into a first chart, a subchart dependency and a hook, reading
someone else's umbrella chart critically. A real platform team doesn't get
those one at a time -- they get handed four components someone hand-wrote
manifests for once (`given/`), a request for a dev environment and a prod
environment that don't fight each other, and a review meeting where they
have to defend every value they exposed. This capstone is that: package a
small "spider platform" -- a target site stand-in, a work queue, a
producer, and a pool of workers -- as ONE Helm chart you write from
scratch, then defend the design in `DESIGN.md`.

The platform is built entirely from this module's fixture app
(`app/app.py`) wearing three different hats plus a plain `redis:7-alpine`:

- **`target`** -- `sandbox20-app:1.0`, `WORK_MODE=server` (default). Stands
  in for the hostile site a real spider platform would crawl. Nothing else
  here calls it; it's a fourth toggleable component your chart has to
  account for even though it's functionally inert in this fixture.
- **`queue`** -- `redis:7-alpine`. The actual work queue.
- **`producer`** -- `sandbox20-app:1.0`, `WORK_MODE=producer`, pushing
  synthetic scrape "URLs" onto the queue at `RATE_PER_S` items/second.
- **`workers`** -- `sandbox20-app:1.0`, `WORK_MODE=consumer`, draining the
  queue at `1000 / PROCESS_MS` items/second per replica.

This is a multi-evening capstone with three checkpoints: get the chart's
structure right offline first (CP1), then prove it actually runs and
survives a dev-to-prod upgrade against the live cluster (CP2), then defend
every design decision in writing and prove the chart still passes both
earlier checkpoints (CP3).

## What's given

- `given/` -- four hand-written, unparameterized manifests (`target-*`,
  `queue-*`, `producer-deployment.yaml`, `workers-deployment.yaml`) showing
  the "before" state: every value hardcoded, nothing toggleable, the queue
  hostname typed in twice as the literal string `redis`. Read
  `given/README.md` first -- it names exactly which hardcoded choices your
  chart must turn into values, and states the rate-capacity arithmetic
  your `values-dev.yaml` / `values-prod.yaml` numbers must respect.
- `chart/` -- a chart skeleton: a real `Chart.yaml` (`name: spider-platform`),
  and `values.yaml` / `values-dev.yaml` / `values-prod.yaml` /
  `templates/*.yaml` / `templates/_helpers.tpl`, all `# TODO(you): ...`
  stubs describing the exact shape each file needs (see the "Chart
  contract" section below for what's graded, not just what's suggested).
- `DESIGN.md` -- an unfilled template with the five sections CP3 checks.
- `hints/` -- three files, escalating from direction to near-pseudocode.
- Three checkpoint validators: `tests/validate_cp1.py`, `validate_cp2.py`,
  `validate_cp3.py`.

## Chart contract

This is what the validators actually check -- read it before you start
naming things, since several checks rely on labels/values existing at
exact paths rather than on any particular resource-naming scheme (you're
free to name your templates and resources however you like, as long as
these hold):

- **Standard labels, every resource**: `app.kubernetes.io/name`,
  `app.kubernetes.io/instance`, `app.kubernetes.io/managed-by`, AND a
  per-component `app.kubernetes.io/component` label with exactly one of
  the values `target`, `queue`, `producer`, `workers`. The validators
  select resources by this component label, not by name.
- **Fullname prefix, every resource**: every rendered object's
  `metadata.name` starts with the release name (`helm template <RELEASE>
  chart/` is invoked with a fixed release name; the standard `helm create`
  `fullname` helper pattern satisfies this automatically).
- **Toggles**: `target.enabled` and `producer.enabled` (both default
  `true`) -- setting either to `false` must remove every resource carrying
  that component's label, and nothing else.
- **`workers` Deployment**: `spec.replicas` from `workers.replicas`;
  `spec.template.spec.containers[0].resources` from `workers.resources`
  (non-empty `requests` AND `limits`, both `cpu` and `memory`, required in
  `values-prod.yaml` specifically -- `values.yaml`'s default may be `{}`);
  readiness probe `httpGet.path`/`port` plus ALL FOUR numeric probe fields
  (`initialDelaySeconds`, `periodSeconds`, `timeoutSeconds`,
  `failureThreshold`) templated from `workers.probes.readiness.*` -- not
  hardcoded, even if a hardcoded number happens to match the default;
  pod template annotation whose key starts with `checksum/`, and whose
  VALUE changes when `workers.processMs` changes (i.e. it's a real hash of
  a config object that actually contains `PROCESS_MS`, not a static
  string).
- **`producer`**: `RATE_PER_S` env var on the producer container equals
  `producer.ratePerS`.
- **Queue wiring, `producer` AND `workers`**: whatever env mechanism you
  use for `REDIS_HOST` (direct `env` or `envFrom` + ConfigMap), it must
  resolve to the QUEUE SERVICE'S OWN RENDERED NAME -- verified by rendering
  the chart under two different release names and checking `REDIS_HOST`
  tracks the queue Service's name in both, rather than being some fixed
  string that happens to match once.
- **`values-dev.yaml` / `values-prod.yaml`**, both at `chart/` root:
  dev renders `workers.replicas == 1`; prod renders `workers.replicas == 3`
  with non-empty `resources` as above; prod's rendered producer
  `RATE_PER_S` is strictly greater than dev's.
- **`helm lint chart/`** and **`helm lint chart/ -f chart/values-prod.yaml`**
  both exit clean.

## What's required

### CP1 -- structure (`validate_cp1.py`, offline, no cluster needed)

Write the full chart -- every file in `chart/templates/`, `values.yaml`,
`values-dev.yaml`, `values-prod.yaml` -- satisfying every bullet in "Chart
contract" above. This checkpoint never installs anything; it's `helm
lint`/`helm template` plus parsing the rendered YAML, so you can iterate
on it fast without touching the cluster at all.

### CP2 -- live behavior (`validate_cp2.py`, needs the cluster)

Your chart actually has to work. The validator:

1. `helm install`s your chart into namespace `t07` (release `t07-spider`)
   with `values-dev.yaml`, waits for every Deployment's rollout.
2. Port-forwards to one `workers` pod's `/metrics` and watches
   `app_processed_total` rise over a ~30s window (the pipeline is actually
   flowing, not just "pods are Running"), while `app_queue_depth` stays
   bounded the whole time (dev's producer rate is calibrated well under
   one worker's drain capacity).
3. `helm upgrade`s the SAME release with `values-prod.yaml`. Checks: all 3
   workers reach Ready; queue depth stays bounded/trending down under the
   new (faster) producer and (larger) worker pool; and -- the part that
   actually tests your labeling -- the `queue` pod's own start time is
   UNCHANGED across the upgrade (nothing about your chart's `queue`
   template may differ between the two values files, and your selectors
   must be stable enough that Helm doesn't recreate it).

The validator cleans up its own install (uninstall + delete namespace) at
the end whether it passes or fails -- reruns are idempotent.

### CP3 -- design review (`validate_cp3.py`)

Fill in every section of `DESIGN.md`. Then the validator re-runs
`validate_cp1.py` and, if that passes, `validate_cp2.py` -- both as real
subprocesses, both must still exit 0. A design memo describing a chart
that no longer lints, or that regressed on the live upgrade behavior,
does not pass this checkpoint either.

## Completion criteria

From this task directory:

```bash
uv run python tests/validate_cp1.py
uv run python tests/validate_cp2.py
uv run python tests/validate_cp3.py
```

Each prints exactly one `PASSED` (with a trailing detail) on success, or
one `NOT PASSED: <reason>` and exits 1 on failure -- no raw tracebacks.
CP2 and CP3 need the `sandbox20` kind cluster up (`bash
../scripts/cluster-up.sh` from the module root if it isn't) and the
fixture images loaded (`bash ../scripts/build-images.sh`).

## Estimated evenings

2-3

## Topics to read up on

- `_helpers.tpl` and the standard `helm create` name/fullname/labels
  pattern -- why charts converge on this shape instead of everyone
  inventing their own
- `{{ if }}` guards around whole template documents as the toggle
  mechanism for optional components
- `checksum/config`-style pod template annotations as the standard trick
  for forcing a rollout when only a referenced ConfigMap changed, not the
  Deployment's own spec
- Deriving one resource's env value from another resource's rendered name
  within the same chart, instead of hardcoding a hostname twice
- `helm upgrade`'s object-level diffing: what makes Kubernetes decide a
  Pod needs recreating vs. what it leaves alone across a values change
- Designing a `values.yaml` surface: which knobs earn their place as a
  value vs. which ones should stay a hardcoded implementation detail

## Off-limits

`.authoring/design.md` (at the module root) holds this module's full
infrastructure contract, including this task's verification approach in
more explicit detail -- spoilers. Don't read it before finishing this
task.
