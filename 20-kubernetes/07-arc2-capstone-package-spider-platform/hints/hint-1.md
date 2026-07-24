# Hint 1

Don't start with `values.yaml`. Start by writing `_helpers.tpl`'s
name/fullname/labels helpers and getting ONE component (pick `queue`,
it's the simplest -- no env wiring, no probes, no toggle) fully rendering
and installable by itself. Every other component is the same four moves
repeated: a helper-driven name, the standard label block plus your own
`app.kubernetes.io/component` label, an env block sourced from `.Values`
instead of literals, and (for `target`/`producer`) an `{{ if
.Values.X.enabled }}` guard around the whole document.

Read `given/README.md` fully before touching `chart/` -- it tells you
exactly which hardcoded values in the "before" manifests need to become
chart values, and gives you the throughput arithmetic
(`workers.replicas * 1000 / workers.processMs` vs. `producer.ratePerS`)
you'll need for `values-dev.yaml` and `values-prod.yaml` later. Getting
that arithmetic wrong doesn't fail CP1 (it's a live-behavior thing) but it
will make CP2 confusing to debug if you skip it now and hit it later.

Two traps worth knowing up front:

- The `workers` Deployment's checksum annotation only means something if
  it's hashing an object that actually CONTAINS the value that changes
  (`PROCESS_MS`). Hash a ConfigMap that has `PROCESS_MS` as one of its
  keys, not something static.
- `REDIS_HOST` on both `producer` and `workers` has to come from the same
  place your `queue` Service template gets its name from -- not two
  separately-typed strings that happen to currently match. If you ever
  find yourself typing the queue's name as a literal string in more than
  one file, that's the hardcoding this task is specifically about
  eliminating.
