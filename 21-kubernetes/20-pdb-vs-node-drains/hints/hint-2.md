# Hint 2

The fleet is 4 replicas. Draining one worker means evicting the (2) replicas
sitting on it. For the service to stay healthy the whole time, you want the
drain to move those pods **one at a time**: evict one, let its replacement
come up Ready on the other worker, then evict the next.

That behavior falls out of a budget that permits exactly **one** replica to
be unavailable at once -- i.e. keep **3 of 4** available. Both of these
express that:

- `minAvailable: 3`
- `maxUnavailable: 1`

Think about the two failure modes the task warns about:

- If you protect *nothing* (`minAvailable: 0`, or a selector that matches no
  pods), the eviction API never blocks, and a drain can remove both replicas
  before their replacements are Ready.
- If you protect *everything* (`minAvailable: 4`), the eviction API can never
  allow a single eviction, because that would drop you to 3 -- below 4. The
  drain blocks forever.

Your PDB's `selector` has to match the pods -- check what label
`given/deployment.yaml` puts on the pod template.
