# Hint 1

Three independent Services, three independent root causes. Diagnose each
one from its own evidence -- `kubectl get endpoints <name>` and
`kubectl describe svc <name>` -- before you touch any YAML. Don't reach for
DNS lookups or curl until you've read what the cluster itself already
tells you about each Service.

`kubectl get endpoints` on all three, side by side, is the fastest way to
sort the three failures into different buckets: one of them will have
literally nothing listed, one will list real pod IPs, and one will list
real pod IPs too -- so Endpoints alone doesn't finish the diagnosis for two
of the three. That's the point: the same-looking "clients can't connect"
symptom has more than one cause here, and the tool that discriminates
between the remaining two isn't `get endpoints`, it's `describe svc` plus
knowing what port the backend actually listens on.

`catalog-backend`'s own Deployment isn't broken -- its readiness probe
already succeeds, which means you can trust the port it's checking as the
real, actual port the app is listening on. Use that as ground truth when
something else's port looks suspicious.
