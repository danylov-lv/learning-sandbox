# Hint 2

You want exactly one thing on the ingress side and three things on the
egress side.

Ingress: `worker` serves nothing, so the correct ingress rule set is the
*empty* one -- `ingress: []` with `Ingress` in `policyTypes`. That is not
the same as omitting `ingress`: listing `Ingress` in `policyTypes` with an
empty rule list means "deny all inbound"; omitting it entirely would leave
inbound wide open. That single choice covers both `decoy -> worker` and
`outsider -> worker` at once -- you never have to mention either of them.

Egress: each entry in `egress:` is an allow rule with two independent
filters that are AND-ed together -- a `to:` (which *peers*) and a `ports:`
(which *ports on those peers*). Omit `ports` and you allow every port to
that peer; omit `to` and you allow that port to every peer. You want both
narrowed on all three legs:

- one leg to `queue`, on the port redis actually listens on;
- one leg to `target`, on the port its *container* listens on (re-read the
  ports gotcha -- it is not the Service's port);
- one leg for DNS, or nothing resolves.

For the two in-namespace peers (`queue`, `target`), a `podSelector` inside
`to:` is enough -- same namespace is the default. Think about what that
implies for the cross-namespace `outsider`: since you never write a rule
whose `to:` reaches into `t14-external`, egress there is denied by omission,
same as `decoy`.
