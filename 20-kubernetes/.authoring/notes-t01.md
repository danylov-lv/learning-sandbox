# Authoring notes -- 01-deployment-service-config

- Stub convention check: a `src/*.yaml` file containing only `#` comment
  lines (no YAML document at all) makes `kubectl apply -f src/` fail with
  `error: no objects passed to apply` and exit 1 -- no YAML parse error,
  no traceback. Confirmed live; validator surfaces this as a single
  `NOT PASSED: kubectl apply -f src/ failed: error: no objects passed to
  apply` line.
- `/env?name=X` in `app/app.py` only echoes names starting with `APP_` or
  `CONFIG_` (403 otherwise) -- this is why the downward-API var is named
  `APP_POD_NAME` (not `POD_NAME` as an earlier sketch of this task had it)
  and why `REQUIRED_ENV` only lists `CONFIG_GREETING,APP_SECRET_TOKEN`
  (the app doesn't need `APP_POD_NAME` to be present to boot -- it's
  always injected by the downward API regardless -- so it stays out of
  `REQUIRED_ENV`).
- `json.dumps` on `app.py`'s `_json` response uses the default separators
  (`", "` / `": "`), so `GET /` renders `"app_version": "1.0"` with a
  space after the colon -- validator checks both spaced and unspaced
  forms defensively anyway.
- `harness.common.delete_ns(..., wait=False)` returns before the
  namespace actually finishes terminating (it's async `kubectl delete
  --wait=false`); a `kubectl get ns t01` immediately after validator exit
  shows `Terminating`, not `NotFound`. It clears on its own within ~15s.
  Not a bug, just worth knowing if you're eyeballing cleanup manually
  right after a validator run.
- Live verification performed against the running `kind-sandbox20`
  cluster (images `sandbox20-app:1.0/2.0/distroless` already loaded):
  1. Stock stubs: `NOT PASSED: kubectl apply -f src/ failed: error: no
     objects passed to apply`, exit 1, zero traceback lines.
  2. Throwaway correct solution written directly into `src/*.yaml`,
     validator run to `PASSED: Deployment/Service/ConfigMap/Secret wired
     correctly: 2/2 ready replicas, 2 Service endpoints, app_version 1.0,
     CONFIG_GREETING/APP_SECRET_TOKEN/APP_POD_NAME sourced correctly`,
     exit 0.
  3. Reverted `src/*.yaml` to the original stub content and verified
     byte-identical via `sha256sum -c` against a hash snapshot taken
     before the throwaway write -- all four files `OK`.
  4. Re-ran the stock validator post-revert: identical `NOT PASSED` line
     as step 1, confirming the revert didn't leave any residue.
  5. Namespace `t01` confirmed deleted (`NotFound`) after a short wait;
     no other namespace touched (`t02` present in the cluster is another
     task's, not mine).
- No reference solution committed anywhere -- the throwaway pass-path
  YAML only ever existed transiently in `src/*.yaml` during verification
  and in this notes file's prose description (no YAML bodies pasted
  here), then was overwritten back to the stub content.
