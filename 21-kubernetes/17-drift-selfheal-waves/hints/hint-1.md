# Hint 1

This task has two deliverables that depend on each other, so build them
in this order: `src/manifests/*.yaml` first, `src/application.yaml`
second.

Unlike task 16, you don't get a pre-seeded Gitea repo to point at — the
validator itself pushes whatever is currently in `src/manifests/` into a
repo it owns (`sandbox20/t17-app.git`) every time it runs, then applies
your `Application` against that. So there's no "log into Gitea and
check" step for you; get the manifests right locally (`kubectl explain
deployment.spec` etc. still work fine offline) and let the validator
handle the git side.

Confirm Argo CD + Gitea are actually up before iterating:

```bash
kubectl --context kind-sandbox20 -n argocd get deploy,sts
```

If anything's missing, go run
`16-argocd-app-by-hand/scripts/install.sh` — this task assumes it
already ran and won't install anything itself.

The four concepts this task actually tests, in the order the validator
checks them: (1) do your three manifests have the right names/labels/
annotations, (2) does your `Application` point at the right repo/
destination, (3) did the sync actually honor wave/hook ordering, (4)
does drifting a live resource out-of-band actually get corrected on its
own. Get 1–3 working before worrying about 4 — there's no point testing
self-heal against an `Application` that isn't even syncing yet.
