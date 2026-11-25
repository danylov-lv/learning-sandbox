# Hint 2

Three of these four workloads (`api`, `worker`, `producer`) share one
dependency: `envFrom: configMapRef: name: pipeline-config`. That's the
narrowing move -- whatever's wrong is either in that ConfigMap, or in how
each Deployment's own `REQUIRED_ENV` list disagrees with what that
ConfigMap actually provides. It is not in the application code (`app.py`
hasn't changed; you can diff it against the module's copy if you want to
rule that out for yourself).

Look at the crashing container's `--previous` log line again: it names
the exact env var(s) it considers missing. Then look at what
`pipeline-config` actually contains (`kubectl -n t11 get configmap
pipeline-config -o yaml`). Somewhere between "what the ConfigMap has" and
"what REQUIRED_ENV demands," there's a mismatch -- and it's not that a key
is missing from the YAML entirely (the ConfigMap has three keys, and the
Deployments demand names that look a lot like those three keys).

Also worth noticing: `producer` reads the exact same broken ConfigMap and
does NOT crash. That's not luck -- open `given/producer.yaml` and compare
its `REQUIRED_ENV` value against `given/api.yaml`'s and
`given/worker.yaml`'s. Different components validate different things at
boot. That asymmetry is *why* only two of the three show the same failure
mode, and it's also why `producer` can be quietly doing the wrong thing
without ever telling you via a crash or an error log.
