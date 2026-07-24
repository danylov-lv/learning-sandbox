# Hint 1

`resources.requests` and `resources.limits` answer two completely
different questions, and mixing them up is the single most common
resourcing mistake:

- **`requests`** is what the *scheduler* uses to decide which node a pod
  can even land on. It reserves that much CPU/memory out of the node's
  allocatable capacity for this pod, whether or not the pod is actually
  using it right now. Set it too high across many pods and you'll see
  pods stuck `Pending` with "insufficient memory" events even though the
  node's *actual* usage looks nowhere near full.
- **`limits`** is what the *kernel* (via cgroups) enforces once the pod is
  already running. A CPU limit throttles you if you go over it -- your
  process slows down, nothing crashes. A **memory limit is not
  throttling** -- there's no such thing as "slow down your memory usage."
  Go over a memory limit and the kernel's OOM killer ends the process,
  full stop, no warning, no grace period.

That asymmetry is why "just set the memory limit really high, it's
free insurance" is not actually free: it doesn't prevent OOMKill (a
genuine leak still eventually blows through *any* fixed limit -- see
Part 2), but it does something else instead -- it reserves capacity other
pods on the node can't use, without a working set anywhere near that
number. That's the entire reason this task states hard caps on the
`limits` you're allowed to write instead of leaving it open-ended: an
answer that "always survives" by setting `limits.memory: 4Gi` isn't a
right-sized answer, it's a different failure mode wearing a green
checkmark.

Before writing any numbers, actually run `given/observe-rightsizing.sh`
(or apply `given/profile-workload.yaml` yourself and run `kubectl top pod
--containers` against it) and look at the real number. Guessing a round
number without measuring is exactly the mistake this task exists to
correct.
