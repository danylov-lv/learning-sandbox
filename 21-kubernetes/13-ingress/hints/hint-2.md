# Hint 2

The Ingress spec nests three levels before you get to the backend:
`spec.rules[]` (one entry per host) -> `.http.paths[]` (one entry per path
under that host) -> `.backend.service` (the Service name + port for that
path). It's easy to flatten this by accident and put `host` and `backend`
as siblings instead of `host` owning a `.http.paths[]` list — that structure
is the actual API shape, not an arbitrary nesting choice, because a single
host can route different paths to different Services.

`backend.service.port` takes `number` (an integer, the Service's `port`,
not `targetPort`) or `name` (if the Service names its port) — pick one, not
both. For this task's given Service, the Service itself doesn't name its
port, so you want `number: 80`.

`pathType` is not optional in `networking.k8s.io/v1` (unlike the old
`extensions/v1beta1` API) — `Prefix` is what you want for a bare `/` that
should match everything under it; `Exact` would only match the literal
string `/` itself.
