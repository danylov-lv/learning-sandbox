"""Shared Gitea plumbing for task 18's validators.

Reuses the admin account task 16 seeded (`gitea-admin` /
`sandbox20-gitea-admin-pw`, documented in .authoring/notes-t16.md) against
the same in-cluster Gitea Deployment/Service (namespace `argocd`). This
module only ever creates NEW repos under the existing `sandbox20` org --
it never touches task 16's `platform-charts` repo.

All functions take `local_port` -- the caller is expected to already be
inside a `harness.common.port_forward("svc/gitea-http", 3000, "argocd")`
block.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

import requests

GITEA_ORG = "sandbox20"
GITEA_ADMIN_USER = "gitea-admin"
GITEA_ADMIN_PASSWORD = "sandbox20-gitea-admin-pw"


def _api(local_port: int, path: str) -> str:
    return f"http://127.0.0.1:{local_port}/api/v1{path}"


def _auth() -> tuple:
    return (GITEA_ADMIN_USER, GITEA_ADMIN_PASSWORD)


def repo_url(local_port: int, repo: str) -> str:
    """Authenticated clone/push URL for a repo, reachable through the caller's port-forward."""
    return f"http://{GITEA_ADMIN_USER}:{GITEA_ADMIN_PASSWORD}@127.0.0.1:{local_port}/{GITEA_ORG}/{repo}.git"


def in_cluster_repo_url(repo: str) -> str:
    """The repoURL an Argo CD Application's spec.source must use -- in-cluster Service DNS."""
    return f"http://gitea-http.argocd.svc.cluster.local:3000/{GITEA_ORG}/{repo}.git"


def repo_exists(local_port: int, repo: str) -> bool:
    resp = requests.get(_api(local_port, f"/repos/{GITEA_ORG}/{repo}"), auth=_auth(), timeout=10)
    return resp.status_code == 200


def ensure_repo(local_port: int, repo: str) -> None:
    if repo_exists(local_port, repo):
        return
    resp = requests.post(
        _api(local_port, f"/orgs/{GITEA_ORG}/repos"),
        auth=_auth(),
        json={"name": repo, "private": False, "auto_init": False},
        timeout=10,
    )
    resp.raise_for_status()


def list_commits(local_port: int, repo: str, branch: str = "main") -> list:
    """Returns [] for a repo that exists but has no commits yet on `branch`
    (fresh/empty repo, or branch not pushed) instead of raising."""
    resp = requests.get(
        _api(local_port, f"/repos/{GITEA_ORG}/{repo}/commits"),
        auth=_auth(),
        params={"sha": branch, "limit": 50},
        timeout=10,
    )
    if resp.status_code != 200:
        return []
    return resp.json()


def _run_git(args: list, cwd: Path) -> subprocess.CompletedProcess:
    result = subprocess.run(
        ["git"] + args, cwd=cwd, capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result


def push_initial(local_port: int, repo: str, src_dir: Path, message: str, branch: str = "main") -> str:
    """Force-pushes a brand-new single-commit history built from src_dir's
    contents. Used only to (re)seed a repo that has no commits yet -- never
    call this on a repo a learner may already have pushed a revert to."""
    workdir = Path(tempfile.mkdtemp(prefix="t18-gitea-"))
    try:
        shutil.copytree(src_dir, workdir, dirs_exist_ok=True)
        _run_git(["init", "-q", "-b", branch], workdir)
        _run_git(["add", "-A"], workdir)
        _run_git(
            ["-c", "user.email=validator@sandbox20.test", "-c", "user.name=task18 validator",
             "commit", "-q", "-m", message],
            workdir,
        )
        _run_git(["push", "-q", "-f", repo_url(local_port, repo), f"{branch}:{branch}"], workdir)
        sha = _run_git(["rev-parse", "HEAD"], workdir).stdout.strip()
        return sha
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def push_commit_on_top(local_port: int, repo: str, mutate_fn, message: str, branch: str = "main") -> str:
    """Clones the repo, lets mutate_fn(workdir: Path) edit files in place,
    commits and pushes (fast-forward, not forced). Returns the new HEAD sha."""
    workdir = Path(tempfile.mkdtemp(prefix="t18-gitea-"))
    try:
        _run_git(["clone", "-q", "--branch", branch, repo_url(local_port, repo), "."], workdir)
        mutate_fn(workdir)
        _run_git(["add", "-A"], workdir)
        _run_git(
            ["-c", "user.email=validator@sandbox20.test", "-c", "user.name=task18 validator",
             "commit", "-q", "-m", message],
            workdir,
        )
        _run_git(["push", "-q", repo_url(local_port, repo), branch], workdir)
        sha = _run_git(["rev-parse", "HEAD"], workdir).stdout.strip()
        return sha
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
