# Hint 1

Run `scripts/install.sh` before you write anything — it takes a couple
of minutes (Argo CD alone is a dozen-plus objects, plus Gitea, plus
seeding a repo) and there's no point iterating on `src/application.yaml`
against a controller that isn't there yet. Confirm everything's up:

```bash
kubectl --context kind-sandbox20 -n argocd get deploy,sts,pods
```

You should see `argocd-server`, `argocd-repo-server`,
`argocd-applicationset-controller`, `argocd-dex-server`,
`argocd-notifications-controller`, `argocd-redis` as Deployments,
`argocd-application-controller` as a StatefulSet, and `gitea` as another
Deployment, all with ready pods.

`kubectl explain application.spec --api-version=argoproj.io/v1alpha1`
(and `--recursive` for the full tree) works once the CRD is installed,
and is a faster, more reliable reference than guessing the shape from
memory or from a screenshot of someone else's `Application`.

The four things that actually matter in the `Application` you write:
where it deploys *from* (`spec.source`), where it deploys *to*
(`spec.destination`), which `AppProject` it belongs to
(`spec.project`), and how syncing is triggered (`spec.syncPolicy`).
Everything else is structure around those four facts.
