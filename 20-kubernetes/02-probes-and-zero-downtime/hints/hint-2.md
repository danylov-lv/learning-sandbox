# Hint 2

**The missing "has it booted" question is `startupProbe`.** While a
`startupProbe` is configured and not yet succeeding, Kubernetes disables
`livenessProbe` and `readinessProbe` entirely for that container — they
don't get evaluated, so they can't kill or mis-route anything during boot.
It has its own `periodSeconds` / `failureThreshold` (and optionally
`initialDelaySeconds`), and what matters is the product:
`periodSeconds * failureThreshold` needs to comfortably exceed the app's
worst-case boot time. You know that number — it's the same env var you're
required to keep.

**The missing "can it serve a request" question is `readinessProbe`** on
`/readyz`. This is what actually gates Service endpoints (`kubectl get
endpoints` only lists pods the readiness check currently likes). Give it a
`periodSeconds` short enough that a pod which just finished its startup
probe gets picked up promptly, not one that leaves it looking ready for
several seconds after it actually is.

**`livenessProbe` retuned:** once a `startupProbe` exists, liveness only
starts being evaluated after startup succeeds — so its own
`initialDelaySeconds` no longer needs to account for the slow boot at all.
Give it enough `periodSeconds` / `failureThreshold` that a single slow
response or a brief blip doesn't kill a healthy pod; this app doesn't fail
`/healthz` under normal operation, so err generous.

**The termination race:** `TERM_IGNORE=1` means the app never reacts to
`SIGTERM` on its own — kubelet has to wait the full
`terminationGracePeriodSeconds` (default 30s) and then `SIGKILL`. That's
correctness-safe for zero-downtime (the pod isn't accepting connections
that were never routed to it) but slow and wasteful, and it's not actually
what makes rollouts drop requests — read the app's own SIGTERM handling
(`app/app.py`, `handle_sigterm` / `_graceful_shutdown`) to see what
`TERM_IGNORE=0` gets you for free. The other acceptable path,
`lifecycle.preStop`, delays *when* the container reacts to termination at
all (a `preStop` hook must finish before `SIGTERM` is even sent) — which
matters because a pod being marked for removal from Service endpoints and
that removal actually reaching every node's routing rules are two
different moments in time, with a gap between them. Whichever path you
pick, `terminationGracePeriodSeconds` needs enough headroom for whatever
delay you introduce plus the app's own drain time — check `TERM_GRACE_S`'s
default in the knob table.
