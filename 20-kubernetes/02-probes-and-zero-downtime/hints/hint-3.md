# Hint 3

Rough shape, not a manifest to paste:

**`startupProbe`** — `httpGet` on `/healthz` (same endpoint liveness uses is
fine here), `periodSeconds` around 2, `failureThreshold` big enough that
`periodSeconds * failureThreshold` clears 8 seconds with real margin (think
low double digits of seconds total, not exactly 8 — probes aren't
millisecond-precise and you don't want to be right at the edge),
`timeoutSeconds` 1-2.

**`readinessProbe`** — `httpGet` on `/readyz`, `periodSeconds` in the 2-3
range, `failureThreshold` small (1-2) since by the time this probe is even
running, `startupProbe` already confirmed the app is up — a failure here
means something regressed, not "still booting."

**`livenessProbe`** — `httpGet` on `/healthz`, `periodSeconds` in the
5-10 range, `failureThreshold` 2-3, `timeoutSeconds` a couple seconds. No
`initialDelaySeconds` needed once `startupProbe` exists.

**Termination**, pick one:

- Delete the `TERM_IGNORE` env entry entirely. Nothing else required — the
  app's default handling already drains in-flight requests before exiting.
- Or keep `TERM_IGNORE: "1"` and add:
  ```
  lifecycle:
    preStop:
      exec:
        command: ["sleep", "<a few seconds>"]
  ```
  plus a pod-level `terminationGracePeriodSeconds` set comfortably above
  that sleep (remember the app's own internal drain cap is a separate knob
  with its own default — check the table — and `preStop` time plus that cap
  both have to fit inside `terminationGracePeriodSeconds` or kubelet SIGKILLs
  mid-drain).

  Whichever path you take, don't take it on faith — run enough load through
  a real rollout to actually see zero drops before you consider it done. A
  handful of requests proves very little; hundreds across a full rollout is
  the kind of sample size that would actually catch a rare race.

**Strategy:**
```
strategy:
  rollingUpdate:
    maxSurge: 1        # or more
    maxUnavailable: 0
```

**What NOT to touch:** the `START_DELAY_S` env entry, the replica count, and
the image. The fix is entirely in probes, termination handling, and rollout
strategy.
