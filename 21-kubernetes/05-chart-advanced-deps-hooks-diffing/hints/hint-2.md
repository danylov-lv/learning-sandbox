# Hint 2

- The dependency's `condition` should point at `queue.enabled` -- meaning
  `chart/values.yaml` needs a top-level `queue:` map with an `enabled: true`
  key underneath it (it already has one; don't rename it). `helm template
  --set queue.enabled=false` is the validator's way of proving the
  condition actually gates something -- if you still see a redis
  Deployment/Service in that render, the condition isn't wired to the value
  you think it is.
- `REDIS_HOST` for both the worker and the hook Job should be `{{ include
  "queue-chart.fullname" . }}` -- called directly, not through some
  `.Subcharts.queue-chart` indirection. Helm's named-template namespace is
  global: a template defined in a dependency's `_helpers.tpl` is callable
  from the parent chart's templates by name, using whatever `.` context
  you pass it (the subchart's helper only needs `.Release.Name`, which is
  identical whether it's the parent or the subchart evaluating it).
- That global-namespace fact cuts both ways: when `queue.enabled` is false,
  the dependency isn't rendered *at all* -- meaning `queue-chart.fullname`
  doesn't exist for that render either. If your Deployment always
  references it unconditionally, `helm template --set queue.enabled=false`
  will error out (not render zero redis resources -- it'll fail to render
  anything). Guard those specific env entries with the same
  `.Values.queue.enabled` check.
- For the hook Job: `helm.sh/hook-weight` is a *string* containing an
  integer (`"-5"`, not `-5`) -- it needs to sort *after* whatever weight you
  see on `given/queue-chart`'s own resources (look at what weight they use,
  and think about why they're hooks at all).
- For the diff: put the two overlay files where the validator expects them
  (`chart/values-dev.yaml`, `chart/values-prod.yaml`), and change at least
  `replicas`, the whole `resources` block, and `queue.key` between them.
  Redirect real `helm template` output to two files and actually run `diff`
  on them -- don't write `DIFF.md` from what you assume the output would
  look like.
