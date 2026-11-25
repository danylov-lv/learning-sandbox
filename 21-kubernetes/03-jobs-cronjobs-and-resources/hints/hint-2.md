# Hint 2

`restartPolicy: Always` — the Deployment default — means "if this
container exits, for any reason, start it again, forever." That's exactly
wrong for a Job: a Job pod is *supposed* to exit when it's done, and
"exited 0" needs to be recognized as success, not restarted into an
infinite loop. Jobs only accept `Never` or `OnFailure` for
`spec.template.spec.restartPolicy` — `Always` is rejected at the API
level. `Never` means "if this pod's container fails, don't restart the
container in place — let the Job controller decide whether to launch a
brand new pod instead," which is the more common choice and what this
task asks for.

`backoffLimit` is a Job-level counter, not a per-pod one: it counts how
many times the Job as a whole has retried after a pod-level failure
before the Job gives up entirely and marks itself `Failed`. Each retry
after a failure is a brand new pod, not a container restart — that
distinction matters when you're reading `kubectl get pods` afterward and
wondering why there are more pod objects than `completions` said there
would be.

QoS class is decided per Kubernetes rules from what a pod's *containers*
set for requests/limits, summed across containers:

- **Guaranteed** — every container sets limits, and for every resource
  (cpu and memory) `requests == limits`.
- **Burstable** — at least one container sets a request or limit, but the
  pod doesn't qualify for Guaranteed (e.g. requests and limits differ, or
  only one of the two is set).
- **BestEffort** — no container sets any request or limit, for anything.

Look at the exact numbers this task asks for on both `requests` and
`limits` and work out for yourself which of the three classes they land
you in before you check `kubectl get pod <name> -o jsonpath='{.status.qosClass}'`
against your own intuition.
