# Authoring notes -- 14-networkpolicy-isolation

Topology (namespace `t14`, plus `outsider` in `t14-external`): `worker`
(WORK_MODE=consumer, `app: worker`), `queue` (redis `redis:t11-repack`,
`app: queue`, :6379), `target` (fixture app `app: target`, container :8080 /
Service :80), `decoy` (fixture app `app: decoy`, same ns, NOT allowed),
`outsider` (fixture app `app: outsider`, in `t14-external`, NOT allowed).

Allow/deny matrix the validator asserts via six one-shot probe Jobs (each
Job carries the impersonated component's exact labels so the learner's
`podSelector` is what actually gets exercised):
- worker -> queue: ALLOW
- worker -> target: ALLOW
- worker -> decoy: DENY
- worker -> outsider (cross-ns): DENY
- decoy -> worker: DENY
- outsider -> worker (cross-ns): DENY

## Verified live (orchestrator, this session)

Stock (unfilled stub) fails cleanly and NON-VACUOUSLY -- with no policy the
negative legs are reachable, so the first negative check fails:
`NOT PASSED: worker -> decoy: expected decoy:80 to be BLOCKED but the
connection succeeded (PROBE_RESULT=CONNECTED) ...`, exit 1, one line.

Reference pass-path proven with a throwaway policy (written in place, run,
reverted byte-identical; stub sha256 `6595c26...b947` matched before/after,
never committed): `PASSED: worker reaches queue+target, worker cannot reach
decoy/outsider, nothing can reach worker`, exit 0.

Reference policy that passed: single NetworkPolicy selecting `app: worker`,
`policyTypes: [Ingress, Egress]`, `ingress: []`, and three egress allow
legs -- (podSelector app:queue, TCP 6379), (podSelector app:target, TCP
8080 -- the CONTAINER port, not the Service's 80), and DNS
(namespaceSelector `kubernetes.io/metadata.name: kube-system` +
podSelector `k8s-app: kube-dns`, UDP 53 AND TCP 53).

## Gotchas

- The DNS-egress trap is real: without the UDP+TCP 53 egress leg to
  CoreDNS, even the ALLOWED worker->queue / worker->target legs fail,
  because the Service name never resolves. Hint-3 calls this out.
- NetworkPolicy `ports` match the port the packet arrives on at the
  destination pod (8080), AFTER the Service VIP has been DNAT'd -- the
  Service's port 80 is invisible to the policy. This is the deliberate
  "ports gotcha" in the stub comment.
- Calico (v3.29.1) is what makes the negative legs actually block; on
  kindnet all six probes would "pass" regardless of the written policy --
  the whole reason this module disables the default CNI.
- CoreDNS in this cluster is labeled `k8s-app=kube-dns` in `kube-system`
  (kubeadm default); `kube-system` carries the automatic
  `kubernetes.io/metadata.name: kube-system` namespace label.
