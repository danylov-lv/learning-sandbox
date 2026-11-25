# Hint 3

Rough shape, not paste-ready YAML:

```
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: t16-app
  namespace: argocd
spec:
  project: default
  source:
    repoURL: http://gitea-http.argocd.svc.cluster.local:3000/sandbox20/platform-charts.git
    targetRevision: main
    path: .
  destination:
    server: https://kubernetes.default.svc
    namespace: t16
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
```

If `uv run python tests/validate.py` still fails after this applies
cleanly, check the Application's own status directly —
`kubectl --context kind-sandbox20 -n argocd get application t16-app -o yaml`
— and look at `status.sync.status`, `status.health.status`, and
`status.conditions`/`status.operationState.message` for whatever Argo CD
itself is complaining about (a repo it can't reach, a chart it can't
parse, an RBAC error against the destination namespace). That's the same
place you'd look at work when a real `Application` gets stuck.

You do not need the `argocd` CLI for any of this — everything above is
inspectable with plain `kubectl` once the CRD is installed, which is
exactly how the validator does it too.
