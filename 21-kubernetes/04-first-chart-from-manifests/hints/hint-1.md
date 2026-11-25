# Hint 1

Start from empty files, not from `helm create`'s scaffold. If you want a
reference to *read* while you work, running `helm create /tmp/scratch-ref`
somewhere outside this repo and opening its generated `_helpers.tpl` /
`deployment.yaml` is genuinely useful -- but read it, don't copy it in.
The whole point of this task is building the muscle memory of writing a
chart's plumbing yourself; pasting in a stranger's boilerplate (with its
own opinions about `serviceAccount`, `ingress`, `autoscaling` blocks this
task doesn't need) defeats that before you've started.

Work in this order, it matches how the pieces depend on each other:

1. `_helpers.tpl` first -- `worker.fullname` and `worker.labels`. Nothing
   else can be written sensibly until these exist, since every other
   template calls into them.
2. `configmap.yaml` -- the simplest resource, one data key.
3. `service.yaml` -- also simple, and it gives you something to check the
   labels/selector consistency against once the Deployment exists.
4. `deployment.yaml` last -- it's the one with the most moving parts (env
   wiring, the checksum annotation, the conditional secret env var).
5. `secret.yaml` -- gate the whole resource behind
   `{{- if .Values.secret.enabled }}`.

Check your work incrementally with `helm template t04-worker chart/` after
each file -- don't write all five blind and debug five files' worth of
errors at once. An empty template renders to nothing and that's fine (it's
valid Go-template output); a template with a typo in it usually renders to
a `nil pointer evaluating interface {}.X` error that tells you exactly
which `.Values.X` path doesn't exist yet.

Read `app/app.py`'s `check_required_env` before touching the Deployment's
`REQUIRED_ENV` env var -- it's the one env var whose value has to *change
shape* depending on `.Values.secret.enabled`, not just substitute a
different literal.
