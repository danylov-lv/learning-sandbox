# Hint 2

`spec.source.repoURL` has to be the *exact* string the install script
printed and README.md documents — it's an in-cluster Kubernetes Service
DNS name (`gitea-http.argocd.svc.cluster.local`), not `localhost`, not
`127.0.0.1`, and not anything you'd port-forward to. That's on purpose:
`argocd-repo-server` runs as a pod inside the cluster, in the `argocd`
namespace, same as Gitea — it resolves that name the same way any pod
resolves any other in-cluster Service, and it doesn't go anywhere near
your machine's network. If you paste `http://localhost:3000/...` here
because that's what you used to `curl` Gitea from your own terminal,
`argocd-repo-server` will fail to resolve it — check `kubectl -n argocd
get application t16-app -o yaml` under `status.conditions` (or the Argo
CD UI's app details) for exactly that kind of DNS failure.

`spec.source.path: .` — the chart was pushed to the repo root, not a
subdirectory. If you're not sure what's actually in there, `helm
template given/chart` locally renders the same thing the seeded copy
in Gitea will.

Argo CD's `Application` objects live in the `argocd` namespace
regardless of which namespace they *deploy into* — don't confuse
`metadata.namespace` (always `argocd` here) with `spec.destination.namespace`
(`t16`, where the actual Deployment/Service end up).
