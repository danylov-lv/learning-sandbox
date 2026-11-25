# Hint 2

**ingest**: the app checks `REQUIRED_ENV` (a comma-separated list of env var
names) at startup and exits 1 if any are missing -- that's the entire
mechanism. `given/broken.yaml` sets `REQUIRED_ENV=CONFIG_DB_URL,CONFIG_QUEUE_URL`
but only defines `CONFIG_DB_URL` as an actual env entry. You need to add a
`CONFIG_QUEUE_URL` env var to the container. Whether it comes from the
existing `ingest-config` ConfigMap (add a key, reference it with
`configMapKeyRef`) or a plain `value:` literal is your call -- either
resolves the crash. What doesn't resolve it in the spirit of this task:
editing `REQUIRED_ENV` itself to drop `CONFIG_QUEUE_URL` from the list. The
pod would come up, but you'd have dodged the actual config problem instead
of fixing it, and the validator checks that string is unchanged.

**render**: once you've confirmed (via the ephemeral container on
`render-debug-target`) which port the app actually bound, look at three
places in the Deployment that all currently say `8080`: the container's
`ports[].containerPort`, the `readinessProbe.httpGet.port`, and -- check
this one yourself rather than assuming -- whether the Service's
`targetPort` needs touching too. It references the container port by name
(`http`), not by number, so think about what that implies for whether the
Service needs to change once you fix the Deployment's port.

Whichever object you're patching, write the full object in your fix file,
not a partial one -- see the comment block already in `src/*.yaml` for why
(`kubectl apply`'s three-way merge will silently strip fields you don't
re-list).
