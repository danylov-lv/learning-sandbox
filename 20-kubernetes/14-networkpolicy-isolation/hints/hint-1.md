# Hint 1

A `NetworkPolicy` only affects pods it *selects* (`spec.podSelector`). If
you write one that selects `app: worker`, only `worker`'s pods change
behavior -- `queue`, `target`, `decoy`, and `outsider` keep their current
"accept from anywhere" behavior no matter what you write, because nothing
selects them.

The moment a `NetworkPolicy` selects a pod for a given direction
(`Ingress`/`Egress`, via `policyTypes`), that direction flips from
"everything allowed" to "nothing allowed except what an explicit rule in
this policy (or any other policy selecting the same pod) permits". There's
no such thing as a "deny" rule in a `NetworkPolicy` -- you get denial by
*omission*. If you don't want `worker` reaching `decoy`, the correct move is
to simply never write a rule that mentions `decoy` at all, not to write an
explicit "deny decoy" block (that's not a thing `NetworkPolicy` YAML has).

Start by reading `given/worker.yaml`, `given/queue.yaml`, and
`given/target.yaml` closely enough to answer, for yourself, before writing
any policy YAML: what label selects `worker`'s pods? What port does `queue`
actually listen on? What port does `target`'s *container* listen on, as
opposed to what port its *Service* exposes?
