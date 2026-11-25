# Hint 2

Narrowing each piece:

- **Warehouse reachability**: two workable routes. Either the special
  hostname docker provides for container-to-host traffic (works from kind
  node containers on Docker Desktop; check whether it resolves from
  *pods*, not just nodes — you may need to map it), or a kind cluster
  config with `extraPortMappings`/host networking arrangements. Test from
  a pod: `kubectl run -it --rm probe --image=postgres:16 -- pg_isready -h <candidate-host> -p 54306`.
- **Image into kind**: `kind load docker-image <name:tag>` and set
  `pullPolicy: IfNotPresent` (or `Never`) — with the default `Always` the
  kubelet will try a registry pull for a tag that only exists node-side
  and fail anyway.
- **Measuring the monitor**: metrics-server is not installed in kind by
  default; either install it (one manifest, plus the kubelet-insecure-tls
  arg for kind) or fall back to `docker stats` on the locally-run
  container — the numbers you need are "idle cpu, peak cpu during a check,
  steady rss", not lab-grade precision.
- **Templating**: you need very little — `.Values` plumbing, standard
  labels applied consistently (the PDB selector must match the pod
  labels; define them once, reference twice), and a Secret for the
  password with the Deployment/CronJob consuming it via `env.valueFrom`.
  If you find yourself copying `helm create`'s `_helpers.tpl` wholesale,
  you're carrying boilerplate this chart doesn't need.
