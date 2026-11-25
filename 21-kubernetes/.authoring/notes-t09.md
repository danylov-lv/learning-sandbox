# Authoring notes -- 09-pending-pod-zoo

- Cluster ground truth confirmed before writing anything: `kubectl get
  nodes --show-labels` shows no `disktype` or
  `topology.kubernetes.io/zone` label on any of the 3 nodes, and `kubectl
  get storageclass` shows exactly one StorageClass, `standard`
  (`rancher.io/local-path`, `WaitForFirstConsumer`, marked default). This
  is why pod-b/pod-c's constraints are unsatisfiable by design (no node
  anywhere carries the label they ask for) and why the reference fix for
  pod-e uses `storageClassName: standard`.
- Stock stub check: `NOT PASSED:
  .../fixes/pod-a.yaml still looks like the unfilled TODO stub`, exit 1,
  no traceback -- the validator's `_check_fixes_not_stub` runs before it
  ever touches the cluster for the fix-application phase, so this fails
  fast without needing a real cluster round-trip for the fixes (though
  `_seed_fixture`/`_verify_fixture_non_vacuous` do run first and did pass
  live against the real cluster).
- Reference pass-path (throwaway, written directly into
  `DIAGNOSIS.md`/`fixes/*.yaml`, sha256 snapshot taken before and after):
  - pod-a: `cpu: "100"` -> `100m`.
  - pod-b: dropped the `nodeSelector: {disktype: ssd}` block entirely.
  - pod-c: dropped the `affinity.nodeAffinity` block entirely.
  - pod-d: kept `nodeSelector: {kubernetes.io/hostname:
    sandbox20-worker2}` unchanged, added one `tolerations` entry
    (`key: s20-t09/quarantine, operator: Equal, value: "true", effect:
    NoSchedule`).
  - pod-e: PVC `storageClassName: fast-ssd` -> `standard`, pod unchanged.
  - Full validator run: `PASSED: all five pods diagnosed and fixed:
    pod-a/b/c/e running, pod-d running on sandbox20-worker2 with the
    quarantine taint still present and tolerated, zoo-data PVC Bound`,
    exit 0.
- Anti-cheat path exercised live: first draft of the pod-d fix (mentally)
  considered would have been to drop the worker2 nodeSelector so the
  scheduler could place it on worker1 or control-plane instead -- the
  validator's `_check_pod_d_placement` explicitly rejects that
  (`spec.nodeName != sandbox20-worker2` or missing `nodeSelector` check),
  confirmed the real reference fix (add-only, node pin kept) is what
  actually passes.
- Reverted `DIAGNOSIS.md` and all five `fixes/*.yaml` to their original
  stub content (these files are untracked in git, so `git checkout`
  wasn't usable for the revert -- rewrote them by hand from the content
  read before the throwaway edit) and verified byte-identical via
  `sha256sum` against the pre-throwaway snapshot -- identical for all six
  files.
- Re-ran the stock validator post-revert: identical `NOT PASSED` line as
  the very first run, confirming the revert left no residue.
- Cleanup confirmed both times (stock-fail run and passing run): `kubectl
  get node sandbox20-worker2 -o jsonpath='{.spec.taints}'` returns empty
  after each validator run, and namespace `t09` was seen `Terminating`
  immediately after the run (deleted via the validator's `finally` block
  regardless of pass/fail).
- No reference solution committed anywhere -- the throwaway pass-path
  content only ever lived transiently in `DIAGNOSIS.md`/`fixes/*.yaml`
  during verification, then was overwritten back to the original stub
  text; field values are documented above as prose, not as pasteable
  YAML bodies.
