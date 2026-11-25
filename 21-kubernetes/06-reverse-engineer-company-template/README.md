# 06 — Reverse-engineer a company template

## Backstory

At work you deploy through a chart someone else designed. You fill in a
values file, open a merge request, Argo CD syncs it, and the pods come
up — or don't, and then you're staring at a `_helpers.tpl` full of
`include` calls you've never had to read before because it always just
worked. This task hands you that chart from the other side: no app code
to write, no cluster to touch, just `given/company-chart/` — a realistic,
complete, company-style umbrella chart for a two-component service
platform (`svc-platform`, components `api` and `worker`) — and a demand
to explain, in writing, every decision it makes and find the ones you'd
push back on.

This is a written task. Nobody runs this chart against a live cluster in
this task (that comes back in later tasks); the validator's only cluster
interaction with your work is `helm lint` / `helm template`, and even
that only reruns against the given fixture chart to make sure it hasn't
been altered into something broken. Everything you're graded on is in
`ANALYSIS.md`.

## What's given

- `given/company-chart/` — the full chart. Read every file in it before
  writing anything:
  - `Chart.yaml`, `values.yaml` (defaults, fully filled in and
    commented), `values-example.yaml` (how a team actually fills this
    chart in for their own service).
  - `templates/_helpers.tpl` — naming, labeling, image-reference, and
    env-merging helpers every other template calls into.
  - `templates/configmap.yaml`, `templates/secret.yaml` — one shared
    ConfigMap and one shared Secret per release.
  - `templates/serviceaccount.yaml`, `templates/rbac.yaml` — one
    ServiceAccount + Role + RoleBinding per component.
  - `templates/deployment.yaml`, `templates/service.yaml`,
    `templates/hpa.yaml` — one of each per component (HPA only where
    `autoscaling.enabled` is true), driven by ranging over
    `.Values.components`.

  This chart is complete and realistic on purpose — it `helm lint`s and
  `helm template`s cleanly, and renders exactly the kind of output a
  company platform team would actually ship. Nothing in it is a stub for
  you to fill in. Do not edit anything under `given/` — your work goes in
  `ANALYSIS.md` only.

- `questions.md` — six hostile-review questions about this specific
  chart. You answer these inline in `ANALYSIS.md` as `### Q1` .. `### Q6`
  under `## Hostile-review responses`.

- `ANALYSIS.md` — an unfilled template with every required section
  already in place as `[fill in ...]`.

## What's required

Fill in `ANALYSIS.md`, in full:

1. **`## How the template is organized`** — what kind of chart this is,
   what a "component" means here, how a team adds one, and what each
   template file is responsible for, in one pass.
2. **`## Every decision explained`** — walk every helper in
   `_helpers.tpl` and every template file, one at a time: what it does,
   why it exists as written, and what would visibly break if it were
   deleted.
3. **`## Questionable decisions`** — this chart has (at least) three
   decisions a careful platform-team reviewer would flag. Find at least
   two of them. For each: what the chart actually does, the concrete
   production failure mode it causes (trace an actual incident, not "bad
   practice" in the abstract), and the specific fix you'd propose.
4. **`## What I would ask the platform team`** — genuine open questions
   this chart doesn't answer on its own.
5. **`## Hostile-review responses`** — answers to `questions.md`'s
   Q1-Q6, each as its own `### Qn` subsection. Restating the question is
   not an answer, and the validator checks for that specifically.

## Completion criteria

From this task directory:

```bash
uv run python tests/validate.py
```

The validator (no cluster needed):

- runs `helm lint` and `helm template` (with defaults, and again with
  `values-example.yaml`) against `given/company-chart/` and asserts both
  succeed, and that the default render produces at least two
  Deployments — protects the fixture, not your writing;
- checks `ANALYSIS.md` has all four required sections, each past a
  generous minimum length, with no leftover `[fill in` markers anywhere
  in the file;
- checks `## Questionable decisions` shows grounded evidence of having
  found at least two of the chart's three planted issues (matched by
  the mechanism you describe, not by exact wording);
- checks all six `### Qn` hostile-review answers are present, each
  substantial and not a restatement of `questions.md`'s question text.

Prints `PASSED` on success, or a single `NOT PASSED: <reason>` line and a
non-zero exit code otherwise — including on the stock, unfilled task.

## Estimated evenings

1

## Topics to read up on

- Helm named templates (`define`/`include`) vs. inline templates, and
  why a company chart pushes almost everything through helpers.
- `range` over a values map to produce N of a resource kind from one
  template file.
- Helm's `tpl` function — rendering a values-supplied string as a
  template with the current context, and what that indirection is for.
- `imagePullPolicy: Always` vs. `IfNotPresent`, and what "the tag is
  mutable" means for reproducibility of a rollout.
- Liveness vs. readiness probes — what should and should not be able to
  fail a liveness check, and why a liveness probe that depends on a
  downstream service is a well-known anti-pattern.
- `checksum/config` / `checksum/secret` pod annotations (the common
  community pattern) and what actually triggers a Deployment rollout in
  Kubernetes versus what doesn't.
- Kubernetes RBAC `Role`/`RoleBinding` scoping, and what "least
  privilege per component" does and doesn't cover on its own.
