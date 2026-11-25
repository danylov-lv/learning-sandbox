# Hint 3

Concrete places to look, one per planted issue category (there are
three; finding two with full mechanism-level explanations is enough to
pass, but look for all three):

- `templates/_helpers.tpl`'s `svc-platform.image` definition, read
  together with its own doc comment immediately above it, and
  `values.yaml`'s comment on `components.api.image.tag`. Render the
  chart with no values file at all and look at what `image:` line
  actually comes out for each component.
- `values.yaml`'s comment on `components.worker.probes.liveness.path`,
  read together with `templates/deployment.yaml`'s `livenessProbe`
  block. Ask what the kubelet does to a container that fails its
  liveness probe `failureThreshold` times in a row, and what "fails" 
  means for a probe whose target endpoint depends on something outside
  the pod itself.
- `templates/secret.yaml` and `templates/deployment.yaml`'s `envFrom`
  block together, plus a search of every template file in the chart for
  the string `checksum`. Compare against what a `kubectl rollout
  restart` versus a plain `kubectl apply` of an updated Secret each do
  to already-running pods.

For the hostile-review questions, `questions.md` already names the
mechanism in each question fairly directly -- the work is tracing it
through the actual chart files and stating it precisely, not guessing
at what kind of problem it "sounds like."
