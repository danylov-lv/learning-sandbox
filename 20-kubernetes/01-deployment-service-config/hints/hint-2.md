# Hint 2

ConfigMap and Secret are the simplest two — both are just `metadata.name`
plus a data map. `ConfigMap.data` is plain strings. `Secret` accepts either
`stringData` (plain strings, Kubernetes base64-encodes them for you on
write) or `data` (values you base64-encode yourself before writing them
into the YAML) — `stringData` is friendlier while hand-writing a manifest.
Don't forget `type: Opaque` on the Secret; it's the general-purpose type
for "arbitrary key/value secret data" as opposed to the built-in typed
secrets Kubernetes uses for things like TLS certs or registry credentials.

For the Deployment, the piece that trips people up first time is
`spec.selector.matchLabels` needing to match `spec.template.metadata.labels`
exactly — the selector is immutable after creation and existing purely so
the Deployment's ReplicaSet knows which pods belong to it, independent of
whatever the template says at any given moment.

For each `env` entry that isn't a literal, the shape is:

```
- name: <ENV_VAR_NAME>
  valueFrom:
    configMapKeyRef:   # or secretKeyRef, or fieldRef
      name: <configmap-or-secret-name>   # not present under fieldRef
      key: <key-name>                    # not present under fieldRef
```

`fieldRef` is different — it has no `name`/`key`, just `fieldPath`. The
pod's own name is available at `metadata.name`; that's the whole downward
API mechanism for this task (no volume mount needed, `env[].valueFrom.
fieldRef` is enough here).

For the Service, `port` is what clients connect to (what `worker:80` means
to another pod in the cluster); `targetPort` is what the container is
actually listening on. `selector` on a Service is a plain label map, not
`matchLabels` — same labels as the pod template, different key name at
this level of the API.
