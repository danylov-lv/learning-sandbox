# Hint 3

The specific class of bug: one key name in `pipeline-config`'s `data:`
map does not exactly match the name the app expects, character for
character. Because it's wired in via `envFrom` (a whole-ConfigMap import)
rather than `env: valueFrom: configMapKeyRef: key: ...` (a single named
key), Kubernetes itself never notices anything is wrong -- there's no such
thing as an "unknown key" for a whole-map import, it just imports whatever
keys happen to exist under whatever names they happen to have. The
Deployment applies clean, the pod schedules clean, the container starts.
The only place this mismatch is ever checked is inside the app's own
`REQUIRED_ENV` startup guard (`app/app.py`, `check_required_env`) -- which
is exactly why it takes a full container start-and-crash cycle to surface
it, rather than a `kubectl apply` error.

Put `given/pipeline-config.yaml`'s three key names and
`given/worker.yaml`'s `REQUIRED_ENV` value side by side and read every
character. Don't skim it -- this is the kind of typo that's genuinely
invisible at a glance and only shows up when you force yourself to
compare letter by letter (or diff the two strings).

Once you've found it: your fix is a ConfigMap correcting that one key
(`src/pipeline-config-fix.yaml`). You do not need to touch any
Deployment's `REQUIRED_ENV` list, and you do not need to change
`REDIS_HOST` or `REDIS_PORT` -- both of those were fine all along, don't
"fix" something that was never broken. After the ConfigMap is corrected,
remember that `api`, `worker`, and `producer` all resolved their env vars
at container start time from the OLD ConfigMap content -- a plain
`kubectl apply` to the ConfigMap alone does not retroactively change a
running container's already-resolved environment. Something has to make
each of those three containers start fresh against the corrected
ConfigMap.
