# Hint 1

Two independent problems, two independent root causes. Don't assume they're
related just because they were both applied in the same migration -- diagnose
each on its own terms, starting from evidence, not from this hint.

For `ingest`: a CrashLoopBackOff means the container starts and then exits,
repeatedly. `kubectl describe pod` will show you the restart count and exit
code; `kubectl logs <pod> --previous` gets you the last attempt's output
(the current attempt may not have logged anything useful yet, or may not
even be running). This image logs a specific, grep-able line when it exits
because of a missing required config value -- read it before you touch any
YAML.

For `render`: a pod stuck `0/1 Running` (not crashing, not Pending, just
never `Ready`) points at a probe, not a crash. `kubectl describe pod` shows
you the readiness probe's target and its recent failure events. The catch:
this container's image has no shell, so the usual `kubectl exec -it <pod>
-- sh` reflex won't work here (try it and read the error). That's not a
bug in the fixture, it's the point -- read up on `kubectl debug` and
ephemeral containers before you reach for anything else.

Don't try to fix `render`'s Deployment pod directly with debug tooling --
use the dedicated `render-debug-target` Pod for that (see README "What's
required"). Whatever you learn about the real listening port from
inspecting that pod applies equally to the Deployment's pod, since they run
identical config.
