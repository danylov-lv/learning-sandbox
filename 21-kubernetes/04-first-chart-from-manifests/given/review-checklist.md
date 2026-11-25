# Values-design review checklist

Not graded by the validator -- this is the review a senior teammate would
actually do on your chart's `values.yaml` before approving the PR. Go
through it yourself before you consider the chart done. It's organized as
questions, not rules, because the right answer sometimes depends on a
tradeoff you have to make a call on.

## What should be a value vs. hardcoded?

- For every hardcoded string/number left in your templates (not sourced
  from `.Values`), can you say *why* it doesn't belong in `values.yaml`?
  A good reason: it's a structural constant of this app (e.g. the
  container's listen port, `8080` -- that's baked into `app/app.py`, not a
  deployment-time choice). A bad reason: "I didn't get around to it yet."
- Conversely, did you turn something into a value that never actually
  varies between dev and prod and never will? Every value is a bit of API
  surface someone else has to learn -- a `values.yaml` with forty keys that
  are all secretly the same in every environment is worse than one with
  ten that actually matter.
- `image.repository` / `image.tag` are values (they change per release and
  per environment). The container's internal port is not (it's a fact
  about the image, not a deployment decision) -- did you accidentally make
  the internal listen port a value too, when only the *Service's* port
  should vary?

## Naming

- Do your value keys read like a sentence when you chain them?
  `image.repository`, `service.port`, `secret.enabled` all read naturally;
  a flat `imageRepo`, `svcPort`, `secretOn` does not, and starts a chart
  that's inconsistent with itself two keys later.
- Booleans: did you name them so `true` reads as "on"/"enabled", not
  something ambiguous like `secret.mode`? `secret.enabled: true` is
  unambiguous. `secret.mode: 1` is not.
- Did you use the same key name for the same concept everywhere, or does
  one template call it `.Values.replicaCount` and another (hypothetically,
  if you'd added a second Deployment) call the equivalent thing
  `.Values.replicas`?

## Defaults safety

- If someone `helm install`s this chart with zero `-f` flags and zero
  `--set` overrides, does anything dangerous happen? (An empty
  `resources: {}` is safe -- it just means "no requests/limits enforced",
  same as not setting the field at all. A `secret.enabled: true` default
  with an empty `secret.token` baked in would NOT be safe -- that's a
  real, empty-string secret shipped to every environment that forgets to
  override it.)
- Does your bare-defaults render actually produce a working Deployment
  (image, replicas, ports all sane), or does it only work once you layer a
  `-f values-*.yaml` on top? A chart's own `values.yaml` should be a
  reasonable, self-sufficient default -- the dev/prod files are overlays,
  not the only way to get a valid render.
- Is `replicaCount`'s default something you'd actually be comfortable
  running if someone forgot to override it (1, not 0 -- and not something
  large that surprises a laptop-scale kind cluster either)?

## Docs

- Does every non-obvious key have a comment in `values.yaml` explaining
  what it does, or would a teammate opening this file cold have to go read
  `templates/deployment.yaml` to find out what `extraEnv` even is?
- If `secret.enabled` gates a whole resource (the Secret itself) plus a
  conditional env var, is that relationship documented anywhere near the
  key, or only discoverable by reading the template?
- Would you be comfortable handing this `values.yaml` to someone who has
  never seen `app/app.py`, with no other context? That's the actual bar --
  "I know what it means" isn't the same claim as "it's documented."
