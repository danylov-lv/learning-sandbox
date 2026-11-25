# Authoring notes -- task 18 (app-of-apps-and-rollback)

Three checkpoints, sharing Arc 5's existing Argo CD (v3.4.5) + Gitea
install (task 16 owns that install; this task never reinstalls anything).
Namespace `t18` is shared between cp1 and cp2 -- neither script ever
deletes it wholesale (only task 16-style single-owner tasks do that);
each checkpoint only creates/deletes the specific Applications it owns.

## Repos created (all new, all under the existing `sandbox20` org)

- `sandbox20/t18-apps.git` -- cp1 only. Force-pushed fresh every run from
  `src/apps/*.yaml` (whatever the learner currently has on disk). This
  repo is the parent Application's directory source.
- `sandbox20/t18-child-chart.git` -- cp1 only. Seeded once (only if it has
  no commits yet) from `given/child-chart/`, a small independent copy of
  the task-16-style fixture chart (image `sandbox20-app:1.0`). Both
  `t18-child-a` and `t18-child-b` deploy this same chart; Argo CD uses
  each child Application's own `metadata.name` as the Helm release name,
  so `.Release.Name`-prefixed resource names naturally differ between the
  two children with zero extra values plumbing.
- `sandbox20/t18-workload.git` -- cp2 only. Deliberately a *separate* chart
  from `t18-child-chart.git` even though both are "the same kind of
  fixture chart" -- keeping cp1's and cp2's git histories in physically
  different repos means a bad-commit-awaiting-revert state in one can
  never bleed into the other checkpoint's grading.

`platform-charts` (task 16's repo) is never read, written, or listed by
anything in this task.

## cp1 -- app of apps

Learner writes `src/root-app.yaml` (parent) + `src/apps/app-a.yaml` +
`src/apps/app-b.yaml` (children, fixed names `t18-child-a`/`t18-child-b`).
The validator:

1. Parses `src/apps/*.yaml` directly off disk with `yaml.safe_load_all`
   (not by reading them back out of git) to get the expected child names
   and validate each one's `spec.destination.namespace == t18` /
   `spec.syncPolicy` presence -- this is the non-vacuous anti-cheat gate:
   an unfilled TODO-comment-only stub parses to zero valid Application
   docs, so "found 0, expected 2" is the exact stock failure line.
2. Separately parses and checks `src/root-app.yaml`'s own spec
   (`repoURL`/`path` -> `t18-apps`, `destination.namespace == argocd` --
   easy to get backwards with the children's `t18` destination, called
   out explicitly in the README and hint-1).
3. Seeds `t18-child-chart.git` (only if empty) and force-pushes
   `src/apps/*.yaml`'s current contents into `t18-apps.git` every run.
4. Deletes any stale `t18-root`/`t18-child-a`/`t18-child-b` Applications
   from a previous run, applies only `src/root-app.yaml`, then
   **waits for the two children to appear on their own** -- the validator
   never applies them directly, so their existence is real proof the
   parent's own reconciliation created them, not an artifact of the test
   harness.
5. Triggers sync (the `operation` field patch trick from task 16) on
   parent + both children, waits for all three Synced/Healthy, and checks
   for >=2 ready Deployments labeled `app.kubernetes.io/name=t18-child` in
   `t18`, with each of the two expected child names appearing as a
   substring of some Deployment name.

Cleans up its own three Applications (cascade) in a `finally`, whether it
passes or fails. Never deletes namespace `t18` itself.

## cp2 -- git revert rollback

No learner-edited file at all for this checkpoint -- the "write" is git
commands against a repo, not YAML. The validator owns
`given/workload-app.yaml` (Application `t18-workload-app`, applied by the
script itself) and `sandbox20/t18-workload.git`.

Two-phase, fully idempotent, re-runnable design (same script both times):

- **Bad-commit identification without any persisted state between runs**:
  rather than remembering "the bad commit's sha" across separate Python
  process invocations, the validator always re-derives it by scanning
  Gitea's commit-list API for a commit whose message **starts with** the
  fixed string `BAD_COMMIT_MESSAGE` (`"BREAK: bump t18-workload image tag
  to a nonexistent version (t18-cp2-bad-commit)"`).
- **Real bug caught live and fixed**: my first cut searched for the
  marker string as a plain substring anywhere in any commit message. That
  broke the very first time I actually performed the revert during
  reference-pass testing: `git revert`'s own default commit message is
  `Revert "<original subject>"` plus `This reverts commit <sha>.` -- which
  **quotes the entire original bad-commit message verbatim**, so the
  revert commit's own message also contains the marker substring. The
  naive substring search found the *revert* commit and misidentified it
  as "the bad commit still un-reverted," producing a false NOT PASSED
  after a real, correct revert. Fixed by requiring `message.startswith(
  BAD_COMMIT_MESSAGE)` for bad-commit identification specifically (a
  revert's message never starts with that string, it starts with
  `Revert "`), while the *revert-detection* check still correctly does a
  substring search for the bad commit's full 40-char sha inside later
  commits' messages (that part was always safe -- no other commit
  message can accidentally contain a random commit's exact 40 hex chars).
  This is exactly the kind of thing "prove the pass-path live" is for;
  documenting it here since a future editor of this file might otherwise
  reintroduce the simpler-looking substring search.
- **Phase 1** (repo has no commit matching the marker yet): pushes a
  known-good commit (`given/workload-chart/`, image `1.0`) then a bad
  commit on top (`values.yaml`'s `tag: "1.0"` string-replaced to
  `9.9-does-not-exist`), applies/syncs `t18-workload-app`, waits (bounded,
  90s) for `health.status` to actually leave `Healthy` (non-vacuous proof
  the fixture really broke something -- ImagePullBackOff on a tag that was
  never built and loaded), then fails with one `NOT PASSED` line
  containing the bad commit's short sha and the exact next steps. This
  first-run "failure" is the intended UX, not a bug.
- **Phase 2** (marker commit found): looks for a later commit whose
  message contains that bad commit's full sha (git's default revert
  message format) and requires it to be the *current tip* of `main`
  (`commits[0]` from Gitea's newest-first commit list) -- a fresh clone
  with the bad commit still at HEAD, unreverted, fails here exactly as
  the design asked. If found, triggers sync and waits (bounded, 300s) for
  Synced/Healthy, then reads the live Deployment's image tag back out of
  the cluster and requires it to be exactly `1.0`.
- Deliberately never re-seeds (force-pushes) once the marker commit
  exists -- this is what makes the script safe to re-run after a learner
  has already pushed their revert; it only ever reads history in that
  branch, never overwrites it.

## cp3 -- mapping + re-verification

`given/work-application.yaml` is a single, richly-annotated multi-source
Application (not deployed anywhere -- points at a fictional Helm repo/
cluster) designed to carry every field named in the task brief: multi-
source with a `ref:`-aliased values source, `ignoreDifferences` (both
`jsonPointers`- and `managedFieldsManagers`-based entries), a named
`spec.destination` (vs. `server`), `syncOptions` (five different flags),
`retry`/`backoff`, `metadata.finalizers`
(`resources-finalizer.argocd.argoproj.io`), and an
`argocd.argoproj.io/sync-wave` annotation on the Application's own
metadata (deliberately chosen so Q3 can ask the learner to distinguish
that from the *same* annotation's very different meaning on a resource
inside a chart -- which is exactly what cp1 just had them build).

`MAPPING.md` mirrors task 06's `ANALYSIS.md` pattern exactly: 6 required
`##` structural sections (graded by `check_sections`, mirroring task06's
`REQUIRED_SECTIONS`/`MIN_CHARS` dict shape) plus a `## Hostile-review
responses` section holding `### Q1`..`### Q6` (graded by `check_answers`
with `questions_path=questions.md` for the anti-copy check, same
`min_original_chars` mechanism task06 uses). `questions.md` is the
learner-facing question list; `check_answers` is given the same text via
`questions_path` purely as the "don't just restate/copy this" reference,
never displayed as instructions on its own.

`validate_cp3.py` re-runs `validate_cp1.py` and `validate_cp2.py` as real
`subprocess.run([sys.executable, ...])` calls (not imported and called as
functions -- keeps each fully independent, matching how a learner would
invoke them by hand) and requires exit 0 + `PASSED` in stdout from both.
Both were included ("(and cp2 if feasible)" from the brief) since cp2's
own idempotent re-check-only-if-already-seeded design makes it a cheap,
safe, side-effect-free re-verification once the learner has already done
their one-time revert.

## Verified live (this session)

All three stock (unfilled) stubs fail cleanly, one `NOT PASSED:` line,
exit 1, no traceback:

```
$ uv run python tests/validate_cp1.py
NOT PASSED: expected exactly 2 valid child Application manifests under src/apps/, found 0 (none) -- each file must be a real Application manifest (apiVersion: argoproj.io/v1alpha1, kind: Application) with its own metadata.name; an unfilled TODO stub contributes nothing

$ uv run python tests/validate_cp2.py   # first run against a fresh repo
NOT PASSED: seeded known-good commit <sha> and a bad commit <sha> in sandbox20/t18-workload.git that flips the image tag to a nonexistent version (9.9-does-not-exist) -- the workload is now unhealthy on purpose. Clone the repo, `git revert <sha>`, push it to main, then re-run this validator. See README.md for the exact clone/push URL and credentials.

$ uv run python tests/validate_cp2.py   # second run, still no revert pushed
NOT PASSED: bad commit <sha> (message contains 't18-cp2-bad-commit') is still un-reverted at the tip of sandbox20/t18-workload.git's main branch -- perform `git revert <sha>` and `git push` (keep git's default 'This reverts commit ...' message intact), then re-run this validator

$ uv run python tests/validate_cp3.py
NOT PASSED: section(s) too short: 'Identity and lifecycle' (352/400 chars), 'Sources: single vs multi-source' (361/900 chars), 'Destination' (223/300 chars), 'Sync policy in depth' (407/900 chars), 'Ignore differences and drift' (448/700 chars), 'Sync waves, hooks, and finalizers' (473/700 chars)
```
(cp3's stock failure is "too short," not "placeholder," because
`check_sections` checks length before placeholder text -- the `[fill in:
...]` guidance prose itself is short of the required minimums. Both are
valid single-line NOT PASSED reasons; this is not a gap.)

Reference pass-path proven live, throwaway correct deliverables in place
for all three checkpoints, in order:

- `sha256sum` recorded for `src/root-app.yaml`, `src/apps/app-a.yaml`,
  `src/apps/app-b.yaml`, `MAPPING.md` before touching any of them.
- cp1: `PASSED: parent Application 't18-root' spawned child Applications
  ['t18-child-a', 't18-child-b'], all reached Synced/Healthy, and each
  landed a ready workload in namespace 't18'`.
- cp2: seeded (first run NOT PASSED as expected) -> manually
  `git clone`/`git revert --no-edit <sha>`/`git push` against the live
  Gitea repo through a real port-forward, exactly the README's documented
  flow -> second re-run (bug described above, found and fixed here) ->
  third re-run: `PASSED: main's HEAD (<sha>) is a revert of the marked bad
  commit (<sha>), and the live workload in namespace 't18' is back on
  image sandbox20-app:1.0, Synced/Healthy`. Re-ran once more afterward
  with no changes -- still `PASSED` (confirms idempotent re-run doesn't
  regress once already reverted).
- cp3 (with throwaway-filled `MAPPING.md` in place, cp1's throwaway
  Applications still live, cp2 already reverted): `PASSED: MAPPING.md
  structurally complete, all 6 hostile-review questions answered; cp1
  re-verified (PASSED: ...); cp2 re-verified (PASSED: ...)`.
- Reverted `src/root-app.yaml`, both `src/apps/*.yaml`, and `MAPPING.md`
  byte-for-byte; `sha256sum` diff against the before-snapshot was empty
  (identical). Re-ran cp1 and cp3 against the reverted stock stubs
  immediately after -- same clean `NOT PASSED` lines as the very first
  run, confirming the revert didn't leave any residue affecting grading.

No reference solution committed anywhere -- all correct YAML/MAPPING.md
content only ever existed on disk transiently during this verification
pass and was reverted before finishing.

## Cleanup performed

- `kubectl -n argocd delete application t18-root t18-child-a t18-child-b
  t18-workload-app --ignore-not-found` (the first three were already gone
  via cp1's own `finally` cleanup from the last cp1 run; only
  `t18-workload-app` still existed).
- `kubectl delete namespace t18 --ignore-not-found` (confirmed gone
  afterward: `Error from server (NotFound): namespaces "t18" not found`).
- Deleted all three Gitea repos created by this task via the Gitea API
  (`DELETE /api/v1/repos/sandbox20/{t18-apps,t18-child-chart,t18-workload}`,
  all returned `204`).
- Confirmed `sandbox20/platform-charts` (task 16's repo) still returns
  `200` -- untouched.
- Confirmed Argo CD (`argocd-server`, `argocd-repo-server`,
  `argocd-applicationset-controller`, `argocd-dex-server`,
  `argocd-notifications-controller`, `argocd-redis` Deployments,
  `argocd-application-controller` StatefulSet) and Gitea (`gitea`
  Deployment) all still 1/1 Ready in namespace `argocd` -- left installed
  for later tasks, per the module contract.

## Gotchas for a future editor

- Do not "simplify" `_find_bad_commit` back to a plain substring search
  for `BAD_MARKER` -- see the cp2 write-up above for exactly why that's
  wrong (it matches the revert commit too, since `git revert`'s default
  message quotes the original subject verbatim).
- `t18-child-chart.git` and `t18-workload.git` are intentionally two
  separate repos with near-identical chart content. Don't consolidate
  them to "reduce duplication" -- that reintroduces the cross-checkpoint
  coupling this design deliberately avoids (a cp2 bad-commit-awaiting-
  revert state would otherwise make cp1's children render as unhealthy
  for an unrelated reason).
- `src/apps/*.yaml` files are read directly off the learner's disk by the
  validator (not round-tripped through git first) specifically so the
  "found 0/2 valid child manifests" stock-failure message can be produced
  without ever needing network/Gitea access -- keep that ordering (parse
  local files and fail fast before touching the cluster or Gitea) if this
  script is ever refactored.
