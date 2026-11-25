# Hint 3

`src/application.yaml` is the same shape as task 16's, pointed at this
task's own repo instead:

```
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: t17-app
  namespace: argocd
spec:
  project: default
  source:
    repoURL: http://gitea-http.argocd.svc.cluster.local:3000/sandbox20/t17-app.git
    targetRevision: main
    path: .
  destination:
    server: https://kubernetes.default.svc
    namespace: t17
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
```

For `src/manifests/*.yaml`, this is only the annotation shape, not full
resources — you still write the Deployment/Service/Job bodies
(containers, ports, selectors) yourself:

```
# on the Job (t17-preflight):
metadata:
  annotations:
    argocd.argoproj.io/hook: PreSync
    argocd.argoproj.io/hook-delete-policy: BeforeHookCreation
    argocd.argoproj.io/sync-wave: "0"

# on the Deployment and Service (both named t17-workload):
metadata:
  annotations:
    argocd.argoproj.io/sync-wave: "1"
```

If `uv run python tests/validate.py` still fails after everything
applies cleanly, check the `Application`'s own status directly —
`kubectl --context kind-sandbox20 -n argocd get application t17-app -o
yaml` — `status.sync.status`, `status.health.status`, and
`status.operationState.syncResult.resources` (per-resource hook phase
and sync result) tell you exactly what Argo CD did and in what order,
the same place you'd look at work.

If the drift check specifically times out even though everything else
passed: double-check `selfHeal: true` is a literal boolean, not the
string `"true"` (YAML parses `selfHeal: "true"` as a string, which Argo
CD's schema — and this validator — both treat as not-true), and confirm
with `kubectl -n t17 get deploy t17-workload -o jsonpath='{.spec.replicas}'`
that the scale-out from the validator actually landed before you assume
self-heal is the problem.
