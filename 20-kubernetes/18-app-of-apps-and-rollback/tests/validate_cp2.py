"""Validator for 20-kubernetes task 18, checkpoint 2 (git revert rollback).

Run from this task directory:

    uv run python tests/validate_cp2.py

Requires Argo CD + Gitea already installed cluster-wide (owned by task 16 --
fails with a clear message pointing at 16-argocd-app-by-hand/scripts/install.sh
if not). This checkpoint owns an Argo CD Application it manages itself
(given/workload-app.yaml, applied by this script -- not learner-authored)
and a Gitea repo it seeds itself (sandbox20/t18-workload.git). The only
thing you write here is git commands against that repo; there is no YAML
to edit.

Two-phase, idempotent flow (re-run this exact command both times):

  Phase 1 (first run against a fresh repo): seeds a known-good commit
  (image sandbox20-app:1.0) and then a scripted BAD commit on top (image
  flipped to a tag that was never built, so the pod can never pull it --
  ImagePullBackOff, health goes non-Healthy). Prints the bad commit's sha
  and instructions, and fails with NOT PASSED -- this is expected; it's
  telling you what to do next, not reporting a bug.

  Phase 2 (after you've cloned the repo, `git revert <sha>`, and pushed):
  re-running this script finds the marked bad commit already seeded, finds
  your revert commit at the tip of main (a real git-history check -- a
  fresh clone with the bad commit still at HEAD, unreverted, fails here),
  triggers an Argo CD sync, and waits (bounded) for the live workload to
  be back on sandbox20-app:1.0 and Healthy.

Never deletes namespace t18 outright (t18 is shared with cp1). Never
re-seeds a repo that already has the bad-commit marker -- this script
will not silently overwrite a revert you already pushed.
"""

from __future__ import annotations

import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))

from harness.common import (  # noqa: E402
    ensure_ns,
    guarded,
    kubectl,
    kubectl_json,
    not_passed,
    passed,
    port_forward,
    require_cluster,
    wait_until,
)

import gitea  # noqa: E402

NS = "t18"
ARGOCD_NS = "argocd"

WORKLOAD_REPO = "t18-workload"
WORKLOAD_CHART_DIR = TASK_ROOT / "given" / "workload-chart"
WORKLOAD_APP_MANIFEST = TASK_ROOT / "given" / "workload-app.yaml"
APP_NAME = "t18-workload-app"

GOOD_TAG = "1.0"
BAD_TAG = "9.9-does-not-exist"
BAD_MARKER = "t18-cp2-bad-commit"
BAD_COMMIT_MESSAGE = f"BREAK: bump t18-workload image tag to a nonexistent version ({BAD_MARKER})"

BREAK_TIMEOUT_S = 90
SYNC_TIMEOUT_S = 300


def _require_argocd_and_gitea():
    for kind, name in (("deployment", "argocd-server"), ("deployment", "argocd-repo-server")):
        d = kubectl_json("get", kind, name, ns=ARGOCD_NS, check=False)
        if not d or not d.get("status", {}).get("readyReplicas", 0):
            not_passed(
                f"Argo CD is not installed/ready (no ready '{name}' Deployment in namespace "
                f"'{ARGOCD_NS}') -- run 16-argocd-app-by-hand/scripts/install.sh first"
            )
    gitea_dep = kubectl_json("get", "deployment", "gitea", ns=ARGOCD_NS, check=False)
    if not gitea_dep or not gitea_dep.get("status", {}).get("readyReplicas", 0):
        not_passed(
            "Gitea is not installed/ready (no ready 'gitea' Deployment in namespace "
            f"'{ARGOCD_NS}') -- run 16-argocd-app-by-hand/scripts/install.sh first"
        )


def _find_bad_commit(commits: list) -> dict | None:
    """Finds the original bad commit, not a later revert of it -- git's
    default revert message quotes the original subject line verbatim
    (`Revert "BREAK: ... (t18-cp2-bad-commit)"`), so a plain substring
    search for BAD_MARKER would match the revert commit too. The bad
    commit's message always starts with BAD_COMMIT_MESSAGE's own prefix;
    a revert of it never does."""
    for c in commits:
        message = c.get("commit", {}).get("message", "")
        if message.startswith(BAD_COMMIT_MESSAGE):
            return c
    return None


def _find_revert_commit(commits: list, bad_sha: str) -> dict | None:
    for c in commits:
        if c.get("sha") == bad_sha:
            continue
        if bad_sha in c.get("commit", {}).get("message", ""):
            return c
    return None


def _break_image_tag(workdir: Path):
    values_path = workdir / "values.yaml"
    text = values_path.read_text(encoding="utf-8")
    if f'tag: "{GOOD_TAG}"' not in text:
        raise RuntimeError(f"expected values.yaml to contain tag: \"{GOOD_TAG}\" before breaking it")
    values_path.write_text(text.replace(f'tag: "{GOOD_TAG}"', f'tag: "{BAD_TAG}"'), encoding="utf-8")


def _ensure_application():
    kubectl("apply", "-f", str(WORKLOAD_APP_MANIFEST), ns=ARGOCD_NS, timeout=60)


def _trigger_sync():
    patch = (
        '{"operation":{"initiatedBy":{"username":"validator"},'
        '"sync":{"syncStrategy":{"hook":{}}}}}'
    )
    kubectl("patch", "application", APP_NAME, "--type", "merge", "-p", patch, ns=ARGOCD_NS, check=False, timeout=30)


def _health_status() -> str | None:
    app = kubectl_json("get", "application.argoproj.io", APP_NAME, ns=ARGOCD_NS, check=False)
    if not app:
        return None
    return app.get("status", {}).get("health", {}).get("status")


def _sync_status() -> str | None:
    app = kubectl_json("get", "application.argoproj.io", APP_NAME, ns=ARGOCD_NS, check=False)
    if not app:
        return None
    return app.get("status", {}).get("sync", {}).get("status")


def _live_image_tag() -> str | None:
    deployments = kubectl_json("get", "deployment", "-l", "app.kubernetes.io/name=t18-workload", ns=NS, check=False)
    items = deployments.get("items", []) if deployments else []
    if not items:
        return None
    containers = items[0].get("spec", {}).get("template", {}).get("spec", {}).get("containers", [])
    if not containers:
        return None
    image = containers[0].get("image", "")
    return image.rsplit(":", 1)[-1] if ":" in image else None


@guarded
def main():
    require_cluster()
    _require_argocd_and_gitea()
    ensure_ns(NS)

    with port_forward("svc/gitea-http", 3000, ARGOCD_NS) as local_port:
        gitea.ensure_repo(local_port, WORKLOAD_REPO)
        commits = gitea.list_commits(local_port, WORKLOAD_REPO)
        bad_commit = _find_bad_commit(commits)

        if bad_commit is None:
            good_sha = gitea.push_initial(
                local_port, WORKLOAD_REPO, WORKLOAD_CHART_DIR,
                f"seed: known-good t18-workload chart (image {GOOD_TAG})",
            )
            bad_sha = gitea.push_commit_on_top(
                local_port, WORKLOAD_REPO, _break_image_tag, BAD_COMMIT_MESSAGE,
            )

            _ensure_application()
            _trigger_sync()
            wait_until(
                lambda: _health_status() not in (None, "Healthy"),
                timeout=BREAK_TIMEOUT_S, interval=3,
                desc=(
                    "the workload to actually go non-Healthy after the bad commit (ImagePullBackOff on "
                    f"{BAD_TAG}) -- if this times out the fixture itself is broken, not your work"
                ),
            )
            not_passed(
                f"seeded known-good commit {good_sha[:12]} and a bad commit {bad_sha[:12]} in "
                f"sandbox20/{WORKLOAD_REPO}.git that flips the image tag to a nonexistent version "
                f"({BAD_TAG}) -- the workload is now unhealthy on purpose. Clone the repo, "
                f"`git revert {bad_sha[:12]}`, push it to main, then re-run this validator. See "
                "README.md for the exact clone/push URL and credentials."
            )

        bad_sha = bad_commit["sha"]
        revert_commit = _find_revert_commit(commits, bad_sha)
        if revert_commit is None:
            not_passed(
                f"bad commit {bad_sha[:12]} (message contains '{BAD_MARKER}') is still un-reverted at "
                f"the tip of sandbox20/{WORKLOAD_REPO}.git's main branch -- perform `git revert "
                f"{bad_sha[:12]}` and `git push` (keep git's default 'This reverts commit ...' message "
                "intact), then re-run this validator"
            )
        head_sha = commits[0]["sha"]
        if head_sha != revert_commit["sha"]:
            not_passed(
                f"found a commit reverting {bad_sha[:12]}, but it is not at the tip of main (HEAD is "
                f"{head_sha[:12]}) -- push your revert commit so it's the latest commit on main"
            )

        _ensure_application()
        _trigger_sync()

    wait_until(
        lambda: _sync_status() == "Synced" and _health_status() == "Healthy",
        timeout=SYNC_TIMEOUT_S, interval=5,
        desc=f"Application '{APP_NAME}' to reach sync.status=Synced and health.status=Healthy after the revert",
    )
    tag = _live_image_tag()
    if tag != GOOD_TAG:
        not_passed(
            f"Application '{APP_NAME}' is Synced/Healthy but the live Deployment's image tag is "
            f"{tag!r}, expected {GOOD_TAG!r} -- did the revert actually restore values.yaml's image.tag?"
        )

    passed(
        f"main's HEAD ({revert_commit['sha'][:12]}) is a revert of the marked bad commit "
        f"({bad_sha[:12]}), and the live workload in namespace '{NS}' is back on image "
        f"sandbox20-app:{GOOD_TAG}, Synced/Healthy"
    )


if __name__ == "__main__":
    main()
