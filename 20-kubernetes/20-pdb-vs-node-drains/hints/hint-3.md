# Hint 3

Concrete shape (you write the YAML):

- `apiVersion: policy/v1`, `kind: PodDisruptionBudget`.
- `spec.selector.matchLabels` matches the web pods' label (`app: web`) --
  the same selector the Deployment uses on its pod template.
- `spec.minAvailable: 3` (or `spec.maxUnavailable: 1`). Do not use both --
  a PDB takes one or the other.

Once applied, confirm the budget actually sees your pods before you trust it:

```bash
kubectl --context kind-sandbox20 -n t20 get pdb
```

The `ALLOWED DISRUPTIONS` column should read `1` and `CURRENT`/`DESIRED`
should reflect 4/3. If `ALLOWED DISRUPTIONS` is `0`, a drain will stall; if
your `EXPECTED PODS` is `0`, your selector doesn't match and you're
protecting nothing. You can watch the eviction happen one pod at a time with
`kubectl -n t20 get pods -o wide -w` in another terminal while the validator
runs (or while you `kubectl drain` a worker yourself with
`--pod-selector app=web --ignore-daemonsets`).
