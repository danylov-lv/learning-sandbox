# 08 -- Secrets management

## Backstory

Two unrelated incidents land on your desk in the same sprint.

First: a teammate pastes a link in chat -- a security scanner flagged their
repo, and when you look, the actual secret isn't even in the files anymore.
Someone noticed the `.env` a while back, deleted it, felt good about it, and
moved on. The scanner still found it, because deleting a file from your
working tree doesn't delete it from `git log`. Every commit that ever
contained that file is still sitting in `.git/`, readable by anyone who
clones the repo, forever, unless someone actively rewrites history (which
nobody did). You've been asked to write the thing that would have caught
this before it shipped: a scanner that looks at a repo the way an attacker
would -- working tree *and* history -- and tells the difference between an
actual leaked credential and the dozen things that merely *look* like one.

Second, unrelated: your own team's `docker-compose.yml` has a database
password sitting in plain text in an `environment:` block, checked into
git, visible to anyone with repo access, rotated approximately never
because rotating it means editing and redeploying a YAML file. The fix
industry settled on years ago is embarrassingly simple: don't put the
*secret* in the config file, put a *path* in the config file, and mount the
real secret as a file at that path at deploy time (Docker calls this
"secrets", Kubernetes calls the same idea "secret volumes", Compose
supports it natively). The application reads a file instead of an env var.
The secret itself never has to touch version control at all.

Both halves below are graded independently; both are required.

## What's given

- `fixture.py` -- a deterministic builder for HALF A's target repo. Running
  it materializes a real, throwaway git repository (`git init`, several
  commits with plausible messages) at `leaky-repo/` simulating a small
  notification service's history: a committed `.env` that was later
  removed (so it survives only in `git log`), a hardcoded DB connection
  string, a signing key baked into a compose file, a cloud-looking access
  key leaked via a debug notebook's saved output, a private key file, and a
  token in a CI workflow -- spread across the tree and history, alongside
  realistic decoys that must NOT be reported. You never run this file
  directly as part of the exercise; `tests/validate.py` calls it for you.
  **This file is the answer key -- see "Off-limits" below.**
- `src/scan.py` -- HALF A's stub. `scan_repo(repo_path)` currently
  `raise NotImplementedError`. Its docstring is the full contract: the
  exact dict schema each finding must have, and how to distinguish a
  working-tree leak from a history-only one.
- `service/docker-compose.yml` -- HALF B's target: a small, realistic
  compose file for a `worker` service with a plaintext `PG_PASSWORD` baked
  into its `environment:` block. You fix this file **in place** (same
  shape as task 06: it's not a stub, it's a working-but-wrong artifact).
- `src/secrets_loader.py` -- HALF B's stub. `load_secret(name)` currently
  `raise NotImplementedError`. Its docstring spells out the `*_FILE`
  env-var convention and the "fail loudly" requirement.
- `tests/validate.py` -- runs both halves and grades them. **This file also
  knows the planted secrets and the exact stock compose value -- see
  "Off-limits".**

## What's required

**Half A -- `src/scan.py`.** Implement `scan_repo(repo_path)` to scan a real
git repository (given its filesystem path) for leaked secrets, returning a
list of findings per the exact schema in the module docstring. It must:

- Scan the **current working tree** for secrets that are still there.
- Scan the **full commit history** (every commit reachable from any ref,
  not just what's currently checked out) for secrets that are NOT in the
  working tree but were committed at some point and are still recoverable
  from `git log`/`git show`.
- Report each finding with the right `source` ("worktree" vs. "history")
  and, for history-only findings, the exact commit sha the secret is
  recoverable from.
- Avoid false positives on realistic decoys planted alongside the real
  leaks: a documented placeholder credential, an empty `.env.example`
  template, a public key, and a changelog entry that happens to contain a
  hex string that looks secret-shaped but isn't one.

**Half B -- `service/docker-compose.yml` + `src/secrets_loader.py`.**

1. Edit `service/docker-compose.yml` in place: remove the plaintext
   `PG_PASSWORD` value entirely (not just rename the key or move it into a
   comment) and replace it with the docker-secrets `*_FILE` convention:
   an env var like `PG_PASSWORD_FILE` whose value is a file path
   (conventionally under `/run/secrets/...`). Add a top-level `secrets:`
   block that sources the secret material from an external `file:` (never
   an inline value), and reference it from the service's own `secrets:`
   list.
2. Implement `load_secret(name)` in `src/secrets_loader.py`: given a
   logical secret name like `"pg_password"`, read the path from
   `PG_PASSWORD_FILE`, read that file, and return its contents (trailing
   newline stripped). It must raise a clear exception -- never return a
   default, never fall back to a plaintext env var -- when the `*_FILE`
   variable is unset or the file it names doesn't exist.

You do not need `docker compose up` this fixture, install `sops`/`age`, or
reach the network -- everything is checked structurally and by calling your
functions directly.

## Completion criteria

Run, from this task's directory:

```bash
uv run python tests/validate.py
```

It builds the Half A fixture fresh, runs your `scan_repo`, grades recall
(every planted secret found, including the history-only one) and precision
(no decoy reported, no dumping every string in the repo as a "finding"),
then checks your Half B compose fix structurally and exercises
`load_secret` directly (happy path, missing env var, missing file, and a
trap: a plaintext `PG_PASSWORD` env var must never be read as a fallback).

Prints `PASSED: <summary>` or `NOT PASSED: <reason>` and exits 0/1.

## Estimated evenings

1

## Topics to read up on

- `git log --all`, `git show <sha>:<path>`, `git ls-tree` -- reading repo
  history and historical file content without checking anything out
- Why deleting a file and committing that deletion does not remove it from
  a repo's history (and what actually does: history rewriting + a forced
  push + everyone re-cloning)
- Common secret shapes and their false-positive traps: connection strings,
  PEM private key headers, cloud-provider access key formats, high-entropy
  token heuristics, and why "looks like base64" alone is not a detector
- Docker Compose `secrets:` (file-sourced) vs. plaintext `environment:`
- The `*_FILE` environment-variable convention (used by many official
  Docker images, e.g. `postgres:*`'s own `POSTGRES_PASSWORD_FILE`)
- Fail-loudly vs. fail-silently error handling for missing configuration
- (Context, not required to implement here) `sops`/`age` and Kubernetes
  Secret volumes as the same idea in other ecosystems

## Off-limits

`.authoring/design.md` (at the module root) holds the harness API contract,
the `shop` schema, the committed ground-truth values, and the verification
philosophy behind every task in this module -- spoilers. Don't read it
before finishing this task.

**`fixture.py` and `tests/validate.py` are also off-limits before finishing
Half A.** `fixture.py` plants every secret on purpose -- it has to, so the
validator can grade you without trusting your own scanner's output -- which
makes it the literal answer key: reading it tells you exactly what to
search for and where. Treat it exactly like `.authoring/design.md`: don't
open it until you've either finished Half A or given up and want to see how
it was built.
