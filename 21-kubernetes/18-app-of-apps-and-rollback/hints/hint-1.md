# Hint 1

Two different "destinations" are easy to mix up in this task, and the
validator's error messages will tell you exactly which one is wrong if you
read them:

- `src/root-app.yaml`'s `spec.destination` is `argocd` -- what this
  Application "deploys" is two more `Application` objects, and those only
  do anything if they land where Argo CD's controller is watching.
- `src/apps/app-a.yaml` and `app-b.yaml`'s `spec.destination` is `t18` --
  these deploy an actual Helm chart (a Deployment + Service), and that
  goes where real workloads go.

Don't apply `src/apps/*.yaml` yourself with `kubectl` -- they're never
meant to exist as live objects applied directly by you. The validator
reads them off disk and pushes their *contents* into a Gitea repo; the
only live object you ever `kubectl apply` in this checkpoint is the parent
in `src/root-app.yaml`. If the two children never show up as
`Application` objects in `argocd`, the parent isn't finding/parsing them
-- check `kubectl -n argocd get application t18-root -o yaml`'s
`status.conditions` for a source-path or repo error before assuming
anything is wrong with the children's own YAML.

`kubectl explain application.spec.source.directory` (once Argo CD's CRD
is installed) documents the directory-source shape the parent needs.
