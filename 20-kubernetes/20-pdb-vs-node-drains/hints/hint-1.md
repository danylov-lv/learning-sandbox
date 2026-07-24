# Hint 1

A `kubectl drain` doesn't force pods off a node come what may -- it uses the
**eviction API**, and the eviction API refuses to remove a pod if doing so
would take a `PodDisruptionBudget` below its floor. So the PDB is the thing
standing between "drain rolls my replicas off one at a time" and "drain takes
them all at once."

Before writing any YAML, get clear on two numbers:

- How many `web` replicas are there, and how many do you need to stay up
  *while one worker is being drained*? Look at `given/deployment.yaml`.
- A PDB expresses that floor either as `minAvailable` (how many must stay up)
  or `maxUnavailable` (how many may go down). Pick whichever you find
  clearer -- they're two ways of saying the same thing.

And check what the drain has to work with: with the node being drained
cordoned, where can the evicted pods actually go? (Look at the Deployment's
`topologySpreadConstraints` -- is the spread hard or soft?)
