# Hint 3

Concrete shape of the four decisions (you still write the YAML yourself):

- **Ingress**: `policyTypes` lists both `Ingress` and `Egress`; `ingress:`
  is the empty list. Done -- both inbound probes are now denied by default.
- **Egress to `queue`**: one `egress` entry whose `to:` is a single
  `podSelector` matching `queue`'s label, and whose `ports:` is TCP on the
  port redis listens on. Confirm the label in `given/queue.yaml` and the
  port in the same file rather than assuming.
- **Egress to `target`**: same structure, matching `target`'s label, TCP on
  the *container* port from `given/target.yaml`'s `PORT` / `containerPort`
  -- not the `80` its Service exposes. NetworkPolicy is evaluated against
  the packet as it arrives at the destination pod, after the Service VIP has
  already been DNAT'd to the real pod port, so the Service port is invisible
  to the policy.
- **Egress for DNS**: one more `egress` entry whose `to:` combines a
  `namespaceSelector` for `kube-system` with a `podSelector` for CoreDNS,
  and whose `ports:` lists *both* UDP 53 and TCP 53. Do not guess CoreDNS's
  labels -- run `kubectl -n kube-system get pods --show-labels` (or
  `get pod -l k8s-app=kube-dns -n kube-system`) and match what you actually
  see. `kube-system` itself has a stable name label
  (`kubernetes.io/metadata.name: kube-system`) you can select on.

Verify each leg independently once it's applied: `kubectl -n t14 exec` a
throwaway pod carrying `app: worker` and try reaching each peer, or just
re-run the validator and read which leg it names. A common first failure is
allowing the two app ports but forgetting DNS -- then even `queue` and
`target` fail, because the name never resolves.
