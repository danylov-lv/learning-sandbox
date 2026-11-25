# Hint 2

**catalog**: `kubectl get endpoints catalog` returns no addresses at all.
Endpoints are populated by matching a Service's `spec.selector` against pod
labels -- if there are zero, the selector doesn't match anything real.
`kubectl get pods --show-labels -n t12` shows you what `catalog-backend`'s
pods are actually labeled; compare that against `catalog`'s
`spec.selector` (`kubectl get svc catalog -o yaml`).

**catalog-batch**: `kubectl get endpoints catalog-batch` does list pod IPs
-- note the port next to them. Now check what port those same pods actually
listen on: `kubectl get deploy catalog-backend -o yaml` (look at
`containerPort`) or `kubectl describe pod -l app=catalog-backend` (look at
the readiness probe's target port, which you already know works). If the
Endpoints port and the pod's real listening port don't match, every
connection through this Service reaches a real pod IP and gets refused
there, because nothing's bound to the port the Service is sending traffic
to.

**catalog-peer**: `kubectl describe svc catalog-peer` -- look at the `IP:`
line. A normal `ClusterIP` Service always has a real address there that
kube-proxy load-balances traffic to. This one doesn't. Look up what a
headless Service (`clusterIP: None`) means for that: no virtual IP gets
allocated, kube-proxy does not program any load-balancing rule for it at
all, and an in-cluster DNS lookup of its name resolves straight to a
backing pod's IP instead of a stable Service IP. A client that connects to
that pod IP on the *Service's* declared port, rather than the pod's actual
port, will find nothing listening there -- there's no translation step to
do it for them anymore.

Whichever Service you're fixing, write the full object in your fix file,
not a partial one -- see the comment block already in each `src/*.yaml` for
why (`kubectl apply`'s three-way merge silently strips fields you don't
re-list), and note the extra gotcha called out in
`catalog-peer-fix.yaml`'s comment about `spec.clusterIP` being immutable.
