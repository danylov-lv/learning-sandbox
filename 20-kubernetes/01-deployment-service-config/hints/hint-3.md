# Hint 3

Rough shape, not paste-ready YAML — you still have to get the indentation
and every name/key consistent across files yourself.

**configmap.yaml**: `kind: ConfigMap`, a `metadata.name`, and a `data` map
with one key (e.g. something like `GREETING:`) whose value is a real
sentence, not the word "TODO" or "changeme" — the validator checks the
value isn't an obvious unfilled placeholder.

**secret.yaml**: `kind: Secret`, `type: Opaque`, a `metadata.name`, and
`stringData` with one key holding any token-looking string.

**deployment.yaml**: `apiVersion: apps/v1`, `kind: Deployment`,
`metadata.name: worker`, `spec.replicas: 2`,
`spec.selector.matchLabels.app: worker`,
`spec.template.metadata.labels.app: worker`. Inside
`spec.template.spec.containers`, one container: `name` (any), `image:
sandbox20-app:1.0`, `imagePullPolicy: IfNotPresent`, `ports: [{containerPort:
8080}]`, and an `env` list with four entries — `CONFIG_GREETING` via
`configMapKeyRef` pointing at your ConfigMap's name/key, `APP_SECRET_TOKEN`
via `secretKeyRef` pointing at your Secret's name/key, `APP_POD_NAME` via
`fieldRef: {fieldPath: metadata.name}`, and `REQUIRED_ENV` as a plain
`value: "CONFIG_GREETING,APP_SECRET_TOKEN"` string.

**service.yaml**: `apiVersion: v1`, `kind: Service`, `metadata.name:
worker`, `spec.type: ClusterIP` (or omit — it's the default),
`spec.selector.app: worker`, `spec.ports: [{port: 80, targetPort: 8080}]`.

Sanity-check order once every file has content: `kubectl apply -f src/`
against a scratch namespace, then `kubectl get pods`, `kubectl describe
pod <name>` if anything isn't `Running`/`Ready`, and `kubectl exec` isn't
even needed — `kubectl logs` on a crash-looping pod will show you the
app's own `FATAL missing required env var(s): ...` line if the
`configMapKeyRef`/`secretKeyRef` names or keys don't actually match what
you wrote in the ConfigMap/Secret.
