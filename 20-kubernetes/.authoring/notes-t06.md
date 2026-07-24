# Authoring notes -- 06-reverse-engineer-company-template

This is the one file in this task allowed to hold the answer key (per
the task spec: "no reference solutions ... here: the ANALYSIS must not
be pre-filled; the chart itself is a GIVEN"). Nothing here is copied
into `ANALYSIS.md`, `README.md`, `questions.md`, or any hint.

## The three planted smells in given/company-chart

All three are in `templates/_helpers.tpl` and `templates/deployment.yaml`,
with the misleading claim always sitting in a comment (in `values.yaml`
or `_helpers.tpl`) next to the code that actually does something
different. None of the three are flagged by `helm lint` -- confirmed
live (see Verification below).

**1. `imagePullPolicy: Always` (hardcoded, no values knob) + image tag
silently defaults to the literal string `"latest"`, despite a comment
claiming it tracks `.Chart.AppVersion`.**
- Where: `_helpers.tpl`'s `svc-platform.image` define; the
  `imagePullPolicy: Always` line in `deployment.yaml`; the misleading
  comment on `components.api.image.tag` / `components.worker.image.tag`
  in `values.yaml`.
- Model answer: an empty `image.tag` plus `imagePullPolicy: Always` means
  the Deployment spec never changes across upgrades (same rendered
  `image:` string every time) but the actual running image can change on
  any pod restart -- node reschedule, OOMKill, manual pod delete --
  because Always re-resolves "latest" at pull time. Two pods in one
  ReplicaSet can run different code with identical specs; no rollout
  history, no audit trail. Fix: `required` the tag in the helper (fail
  the render on empty), drop the "latest" fallback; if a floating dev tag
  is wanted, make `pullPolicy` an explicit values field, not a silent
  helper fallback.
- Grading keyword group: `pull\s*policy`, `always`, `latest` (all three
  must hit).

**2. Liveness probe hits `/health/deep`, documented as checking DB +
queue connectivity.**
- Where: `components.*.probes.liveness.path` default `/health/deep` in
  `values.yaml`, with the "checks DB + queue connectivity" comment; wired
  into `livenessProbe.httpGet.path` in `deployment.yaml`.
- Model answer: liveness failing `failureThreshold` times kills and
  restarts the container -- correct for a wedged process, wrong for a
  probe that fails because a downstream dependency is down. A DB blip
  fails liveness on every replica of every component roughly
  simultaneously (they all check the same DB), so the kubelet restarts
  the whole fleet at once; the new pods still can't reach the DB, fail
  liveness again, and the Deployment enters a synchronized crash-restart
  loop for as long as the DB stays down -- worse with more replicas
  (bigger simultaneous reconnect storm hitting the DB's connection pool
  right as it's recovering). Fix: liveness hits a shallow
  process-alive-only endpoint (e.g. `/healthz`); `/health/deep` belongs
  only on `readinessProbe`, where failing just pulls the pod out of the
  Service's endpoints without killing it.
- Grading keyword group: `liveness`, and one of `cascad|restart storm|dependenc`.

**3. One shared Secret (`<fullname>-shared`) mounted via `envFrom` by
every component, and no `checksum/config` or `checksum/secret` pod
annotation anywhere in the chart.**
- Where: `templates/secret.yaml` (single Secret, no per-component
  scoping); every component's `envFrom.secretRef` in `deployment.yaml`;
  absence of any `checksum` annotation in the pod template.
- Model answer (two-sided): (a) rotating one credential in
  `sharedSecret.data` for one component's incident actually rewrites the
  credential every component reads -- there's no way to rotate `api`'s
  copy of `DB_PASSWORD` without also rewriting `worker`'s. (b) because
  there's no checksum annotation on the pod template, editing the
  Secret's contents doesn't change the Deployment spec at all, so Argo
  CD/`helm upgrade` sees nothing to roll out -- already-running pods keep
  the old value in-process indefinitely; only newly created pods (HPA
  scale-up, node reschedule) pick up the new value. Result: a fleet
  silently split between old/new credentials with nothing surfacing the
  split. Fix: split the shared Secret into per-component Secrets (or at
  least per-concern), and add a `checksum/secret` + `checksum/config`
  pod-template annotation computed from a hash of the values (the common
  community pattern) so a content-only edit still forces a rollout.
- Grading keyword group: `checksum`, and one of `secret|rotat|roll`.

Validator requires at least 2 of these 3 keyword groups to hit inside the
"Questionable decisions" section body (case-insensitive regex, `re.search`
per pattern within a group, OR across the 3 groups' pass/fail >= 2).

## questions.md model answers (short form)

- Q1: global.env change -> mergedEnv helper output changes -> pod spec
  env block changes -> real rollout. sharedConfig/sharedSecret *data*
  change -> object contents change but pod spec (which only references
  the object by name) doesn't -> no rollout, because no checksum
  annotation. This is smell 3's mechanism, asked from the "config drift"
  angle.
- Q2: full restart-storm chain for smell 2, plus "why worse with more
  replicas" (bigger simultaneous reconnect storm against the recovering
  DB).
- Q3: smell 1's mechanism, focused on the "same chart version twice, same
  values, different running image" framing.
- Q4: smell 3's mechanism, focused on the "rotate one component's
  credential, actually rewrite everyone's" framing plus the "does anyone
  find out" angle (no, not without already knowing to look).
- Q5: not a plant -- a genuine, defensible design decision (tpl
  indirection on podAnnotations). Asks for the real tradeoff: lets
  release/chart context flow into an annotation value; risk is a broken
  template expression in one component's annotations is a hard render
  failure for the whole chart, not a scoped/soft failure.
- Q6: not a plant on its own -- per-component RBAC is a genuinely good
  decision -- but the question asks the learner to connect it to smell 3:
  RBAC scopes API access tightly per component, but the shared Secret
  hands every component's process env every credential regardless,
  undermining the least-privilege story RBAC is telling.

## Validator calibration note (relevant if this pattern is reused
elsewhere)

`check_answers`'s originality gate (`min_original_chars`) only measures
non-matching characters against `questions.md`'s raw text via
`difflib.SequenceMatcher` -- it does not measure semantic content. A
cheat answer built as "verbatim question text" + "generic filler
sentence" scores its entire filler sentence as original characters,
because that sentence literally does not appear in questions.md. With
the module's usual defaults (`min_chars=200`, `min_original_chars=120`),
a single ~200-character generic filler sentence appended to the question
text was measured to pass both gates outright (PASSED) in live testing
-- confirmed before tightening this. This task's call was tightened to
`min_chars=300, min_original_chars=300` specifically so a "restate + one
filler sentence" cheat measurably fails (confirmed: the same filler
sentence now produces "NOT PASSED: ... (mostly restates the question:
~204/300 characters of your own)" for all 6 questions), while every
genuine answer written for verification (975-1295 original characters
each, 6-for-6) clears the bar with wide margin. A sufficiently long,
plausible-sounding invented essay could in principle still clear 300
original characters without answering the question -- at that length,
though, producing it is closer to doing the actual work than to
cheating, which is the same tradeoff this module's other doc-gated tasks
already accept.

## Verification performed (live, this session)

1. `helm lint given/company-chart` (defaults and with
   `values-example.yaml`): 0 chart(s) failed, both times. No lint
   warning flags any of the 3 plants (confirms "subtle, findable by
   reading, not flagged by lint").
2. `helm template` (defaults and with `values-example.yaml`): both
   render cleanly (exit 0); confirmed 2 Deployments, 2 Services, 2
   ServiceAccounts, 2 Role/RoleBinding pairs, 1 shared ConfigMap, 1
   shared Secret, and the HPA count matching each render's autoscaling
   settings (worker only with defaults; both with values-example.yaml,
   which turns api autoscaling on).
3. Plant presence confirmed by grepping the default-values render:
   - `imagePullPolicy: Always` x2 (api, worker).
   - `image: registry.internal.example.com/platform/svc-platform-api:latest`
     and the worker equivalent (tag defaults to "latest", not
     Chart.AppVersion "1.4.2", despite the comment).
   - `path: /health/deep` x2 (liveness, both components).
   - Secret name `<release>-svc-platform-shared` referenced by name 6x
     (1 ConfigMap metadata, 1 Secret metadata, 2x envFrom per component
     x2 components).
   - Zero matches anywhere in rendered output for the substring
     `checksum`.
4. Stock `ANALYSIS.md` (unfilled template): single `NOT PASSED: section(s)
   too short: 'Every decision explained' (571/1200 chars), 'Questionable
   decisions' (372/600 chars), 'What I would ask the platform team'
   (265/300 chars)`, exit 1, no traceback.
5. Throwaway, fully genuine filled `ANALYSIS.md` (written to scratch,
   copied in-place only for this test, sha256-tracked before/after):
   `PASSED: fixture chart lints/renders cleanly; ANALYSIS.md structurally
   complete; 2/3 planted issues identified; all 6 hostile-review
   questions answered`, exit 0. (The genuine answer discussed 2 of the 3
   plants explicitly in "Questionable decisions" -- 2/3 is the passing
   bar per spec, confirmed working as intended.)
6. Cheat attempt (verbatim question text + one generic filler sentence
   for all 6 answers, everything else identical to the genuine pass-path
   doc): `NOT PASSED: only 0/6 required hostile-review question(s)
   answered; unanswered or insufficient: Q1 (mostly restates the
   question: 204/300 characters of your own), ...` for all 6, exit 1.
7. `ANALYSIS.md` reverted to the original stock template content after
   every throwaway write; verified byte-identical via `sha256sum` against
   a hash snapshot taken before any throwaway write (identical hash
   before and after all of the above). Re-ran the stock validator
   post-revert: identical `NOT PASSED` line as step 4.
8. `git status` in the repo confirmed clean of scratch/throwaway residue
   after this session -- all throwaway files lived only under
   `/c/Users/Leonid/AppData/Local/Temp/s20-t06-scratch`, never inside the
   repo.
