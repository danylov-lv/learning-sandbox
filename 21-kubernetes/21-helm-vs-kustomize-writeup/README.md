# 21 — Helm vs Kustomize writeup

## Backstory

By this point you've hand-written a Helm chart from scratch (arc 2 —
`04-first-chart-from-manifests`, `05-chart-advanced-deps-hooks-diffing`,
`07-arc2-capstone-package-spider-platform`), and you've watched Argo CD
render and sync a chart's output straight from git (arc 5 —
`16-argocd-app-by-hand` onward). At work you already ship through a Helm
chart plus an Argo CD `Application` template someone else designed. What
you haven't had to do yet is defend that choice — or admit it might be
wrong for a given service.

This task is that defense. No manifests to write, no cluster to touch —
just a reasoned, written comparison of Helm and Kustomize, graded on
whether you actually understand *why* each tool works the way it does,
not on producing the "correct" verdict. There isn't one correct verdict
here: a good answer for a 3-service platform can be a bad answer for a
40-service one, and the validator is built around that — it checks that
you reasoned concretely, not that you picked a particular winner.

## What's required

Fill in `COMPARISON.md`, in full:

1. **`## Mental models`** — how Helm's templating model actually works
   (Go templates + `values.yaml` producing text, rendered before the
   YAML is ever parsed as Kubernetes objects) versus Kustomize's overlay
   model (real, syntactically valid YAML at every layer; `bases` +
   `overlays`/`components` composed via strategic-merge and JSON 6902
   patches, no text templating at all). State the actual mechanical
   difference, not just "one templates and one patches."
2. **`## Where Helm wins`** — concrete scenarios where Helm's model is
   the better fit: packaging for reuse across teams/orgs, dependency
   management (subcharts, `Chart.yaml` `dependencies`), lifecycle hooks,
   a public chart ecosystem to consume from.
3. **`## Where Kustomize wins`** — concrete scenarios where Kustomize's
   model is the better fit: no templating language to fight with, plain
   YAML that `kubectl diff`/`kubectl apply -k` understands natively,
   overlays that stay readable without a rendering step, GitOps
   controllers that can show a real diff against the target state.
4. **`## Decision`** — for a stated, specific scenario (you pick one:
   your own team's real setup, or the 8-microservices/3-environments
   scenario from `questions.md` Q1), which tool you'd actually choose
   and why — including what you'd give up by not picking the other one.
5. **`## Hostile review`** — answers to `questions.md`'s Q1–Q5, each as
   its own `### Qn` subsection. Restating the question is not an answer;
   the validator checks for that specifically.

## Completion criteria

From this task directory:

```bash
uv run python tests/validate.py
```

The validator (no cluster needed, pure text/structure checks):

- checks `COMPARISON.md` has all four required `##` sections, each past
  a generous minimum length, with no leftover `[fill in` markers
  anywhere in the file;
- checks the document as a whole uses enough of the module's grounding
  vocabulary (chart/values/overlay/patch/hook/base/... — see
  `tests/validate.py` for the exact list) that a passing answer can't be
  vocabulary-free hand-waving;
- checks all five `### Qn` hostile-review answers in `## Hostile review`
  are present, each substantial and not a restatement of
  `questions.md`'s question text (measured character-by-character
  against the question text, not just "isn't identical").

Prints `PASSED` on success, or a single `NOT PASSED: <reason>` line and a
non-zero exit code otherwise — including on the stock, unfilled task.

## Estimated evenings

1

## Topics to read up on

- Helm's templating model: Go `text/template` + Sprig functions,
  `values.yaml` merge order (chart defaults, `-f` files, `--set`,
  parent-chart globals), and what "the output must parse as valid YAML
  *after* rendering" implies about what can and can't go wrong.
- Kustomize's overlay model: `bases`, `overlays`, and (newer) reusable
  `components`; strategic-merge patches vs JSON 6902 patches vs the
  `patches`/`patchesStrategicMerge`/`images`/`replacements` fields.
- DRY-via-parameterization (Helm's `values.yaml` + conditionals) versus
  DRY-via-composition (Kustomize's base + overlay diff) — where each
  approach hides complexity well and where it hides it badly.
- Chart dependencies (`Chart.yaml` `dependencies`, subcharts, `global`
  values) versus Kustomize `bases`/`components` — what "shared" means in
  each model and how deeply a downstream user can override an upstream
  default.
- Helm lifecycle hooks (`pre-install`, `pre-upgrade`, `post-delete`,
  hook weights/deletion policies) and the fact that Kustomize has no
  hook mechanism at all — what that forces you to do instead (a
  separate Job applied out-of-band, an Argo CD sync-wave/hook
  annotation, a CI step).
- Secret handling in each: Helm's plain `Secret` templates plus the
  `helm-secrets`/SOPS ecosystem versus Kustomize's built-in
  `secretGenerator` (and why "built-in" here does not mean "encrypted at
  rest in git" for either tool without an add-on).
- Argo CD's native support for both (`spec.source.helm.valueFiles` /
  `spec.source.kustomize.*`) and what changes about the `Application`
  CR's `source` block, and about diffing, depending on which one you
  point it at.
- `checksum/config`-style annotations as a Helm chart convention versus
  what forces a rollout under Kustomize when a `ConfigMap`/`Secret`'s
  content changes (`configMapGenerator`/`secretGenerator`'s
  content-hash suffix behavior).
