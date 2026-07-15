"""Validator for 12-api-engineering task 08 -- secrets management.

Two independent halves, BOTH required for PASSED:

  HALF A ("find the leaked secret"): builds a throwaway, deterministic git
  repo (fixture.build_leaky_repo) containing 6 planted secret leaks spread
  across the working tree AND git history (one secret was committed and
  later removed -- it survives only in history), plus 4 realistic decoys
  that must NOT be reported. Runs the learner's `src/scan.py:scan_repo()`
  against it and grades BOTH recall (every planted secret found, with the
  right source/commit) and precision (no decoy reported, no firehose of
  noise). The expected set comes from fixture.py's own manifest -- this
  validator never trusts the scanner's own output as ground truth.

  HALF B ("no secrets in env/compose files"): checks that
  service/docker-compose.yml (which the learner edits in place, same shape
  as task 06's fix-in-place) no longer contains the stock plaintext secret,
  uses the docker-secrets `*_FILE` env var convention with a file-sourced
  top-level `secrets:` block, and that `src/secrets_loader.py`'s
  `load_secret()` actually reads from the file mount and FAILS LOUDLY
  (raises) rather than silently defaulting when the env var or file is
  missing -- including a trap: it must never fall back to a plaintext,
  non-`_FILE` env var that happens to be set.

On the unmodified stubs, whichever half's function is called first raises
NotImplementedError -> single-line `NOT PASSED: scaffold not implemented
yet (NotImplementedError)`. Run from this task's directory:

    uv run python tests/validate.py
"""

import os
import sys
import tempfile
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))
sys.path.insert(0, str(TASK_ROOT))

from harness.common import guarded, not_passed, passed  # noqa: E402

from fixture import build_leaky_repo  # noqa: E402
from src.scan import scan_repo  # noqa: E402
from src.secrets_loader import STOCK_PLAINTEXT_MARKER, load_secret  # noqa: E402

COMPOSE_PATH = TASK_ROOT / "service" / "docker-compose.yml"

# 6 real secrets + generous slack -- a scanner that just reports everything
# (recall without precision) still trips this well before it could hide
# behind "well, technically all 6 are somewhere in there".
MAX_ALLOWED_FINDINGS = 10


def _normalize_path(p):
    s = str(p).strip().replace("\\", "/")
    if s.startswith("./"):
        s = s[2:]
    return s


def _check_finding_schema(findings):
    if not isinstance(findings, list):
        not_passed(f"scan_repo() must return a list, got {type(findings).__name__}")
    for f in findings:
        if not isinstance(f, dict):
            not_passed(f"scan_repo() finding is not a dict: {f!r}")
        for key in ("type", "path", "value", "source"):
            if key not in f:
                not_passed(f"finding {f!r} is missing required key {key!r}")
        if f["source"] not in ("worktree", "history"):
            not_passed(f"finding {f!r} has source={f['source']!r}, expected 'worktree' or 'history'")
        if f["source"] == "history" and not f.get("commit"):
            not_passed(f"finding {f!r} has source='history' but no non-empty 'commit'")


def _check_recall(findings, secrets):
    for secret in secrets:
        candidates = [
            f
            for f in findings
            if _normalize_path(f.get("path", "")) == secret["path"]
            and f.get("source") == secret["source"]
        ]
        if secret["source"] == "history":
            valid_commits = set(secret.get("valid_commits") or [secret["commit"]])
            candidates = [f for f in candidates if f.get("commit") in valid_commits]
        if secret["value"] is not None:
            candidates = [f for f in candidates if secret["value"] in str(f.get("value", ""))]
        else:
            candidates = [f for f in candidates if "PRIVATE KEY" in str(f.get("value", "")).upper()]
        if not candidates:
            where = f" commit={secret['commit']!r}" if secret["source"] == "history" else ""
            not_passed(
                f"missed planted secret {secret['id']!r} ({secret['class']}) at "
                f"path={secret['path']!r} source={secret['source']!r}{where}"
            )


def _check_precision(findings, decoys, secrets):
    decoy_paths = {d["path"] for d in decoys}
    for f in findings:
        path = _normalize_path(f.get("path", ""))
        if path in decoy_paths:
            not_passed(
                f"reported a decoy as a leaked secret: path={path!r} value={f.get('value')!r} -- "
                f"decoys (a documented example key, an empty .env.example, a public key, a "
                f"changelog hash) must not be flagged"
            )
    if len(findings) > MAX_ALLOWED_FINDINGS:
        not_passed(
            f"scan_repo() returned {len(findings)} findings for {len(secrets)} planted secrets -- "
            f"that looks like over-reporting rather than distinguishing real secrets from noise"
        )


def _run_half_a():
    manifest = build_leaky_repo()
    repo_dir = manifest["repo_dir"]
    secrets = manifest["secrets"]
    decoys = manifest["decoys"]

    findings = scan_repo(repo_dir)

    _check_finding_schema(findings)
    _check_recall(findings, secrets)
    _check_precision(findings, decoys, secrets)

    return (
        f"half A: {len(secrets)}/{len(secrets)} planted secrets found "
        f"(incl. the history-only one), 0/{len(decoys)} decoys reported "
        f"({len(findings)} total findings)"
    )


def _check_compose_structure():
    import yaml

    if not COMPOSE_PATH.exists():
        not_passed(f"{COMPOSE_PATH} is missing")

    text = COMPOSE_PATH.read_text(encoding="utf-8")
    if STOCK_PLAINTEXT_MARKER in text:
        not_passed(
            f"{COMPOSE_PATH} still contains the stock plaintext secret {STOCK_PLAINTEXT_MARKER!r} -- "
            f"replace it with a *_FILE mount, don't just rename the key or move it to a comment"
        )

    try:
        doc = yaml.safe_load(text)
    except Exception as e:
        not_passed(f"{COMPOSE_PATH} is not valid YAML: {e}")

    services = doc.get("services") if isinstance(doc, dict) else None
    if not services:
        not_passed(f"{COMPOSE_PATH} has no 'services' block")

    found_file_var = False
    any_service_references_secret = False
    for svc_name, svc in services.items():
        if not isinstance(svc, dict):
            continue
        env = svc.get("environment")
        env_items = []
        if isinstance(env, dict):
            env_items = list(env.items())
        elif isinstance(env, list):
            for item in env:
                if isinstance(item, str) and "=" in item:
                    k, v = item.split("=", 1)
                    env_items.append((k, v))
        for k, v in env_items:
            k_upper = str(k).upper()
            if k_upper == "PG_PASSWORD":
                not_passed(
                    f"service {svc_name!r} still sets a plaintext PG_PASSWORD env var -- "
                    f"use a PG_PASSWORD_FILE mount instead"
                )
            if k_upper.endswith("_FILE") and "PASSWORD" in k_upper:
                found_file_var = True
                if not str(v).startswith("/"):
                    not_passed(
                        f"service {svc_name!r} sets {k}={v!r} -- a docker-secrets file mount "
                        f"should be an absolute path (conventionally under /run/secrets/)"
                    )
        if svc.get("secrets"):
            any_service_references_secret = True

    if not found_file_var:
        not_passed(
            f"{COMPOSE_PATH}: no '*_FILE'-style secret env var found -- expected something like "
            f"PG_PASSWORD_FILE=/run/secrets/pg_password"
        )
    if not any_service_references_secret:
        not_passed(f"{COMPOSE_PATH}: no service lists the secret under its own 'secrets:' entry")

    top_secrets = doc.get("secrets")
    if not isinstance(top_secrets, dict) or not top_secrets:
        not_passed(
            f"{COMPOSE_PATH}: no top-level 'secrets:' block -- docker-compose secrets must be "
            f"declared there, sourced from an external file"
        )
    for sec_name, sec_def in top_secrets.items():
        if not isinstance(sec_def, dict) or "file" not in sec_def:
            not_passed(
                f"{COMPOSE_PATH}: secrets.{sec_name} ({sec_def!r}) is not file-sourced -- "
                f"docker-compose secrets are sourced from an external 'file:', never an inline value"
            )

    return "compose fixture has no plaintext secret, uses *_FILE convention + file-sourced secrets: block"


def _check_loader():
    old_env = dict(os.environ)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            secret_path = Path(tmp) / "pg_password"
            secret_path.write_text("hunter2-test-pw\n", encoding="utf-8", newline="\n")

            os.environ["PG_PASSWORD_FILE"] = str(secret_path)
            os.environ.pop("PG_PASSWORD", None)
            value = load_secret("pg_password")
            if value != "hunter2-test-pw":
                not_passed(
                    f"load_secret('pg_password') returned {value!r}, expected 'hunter2-test-pw' "
                    f"(read from the file at PG_PASSWORD_FILE, trailing newline stripped)"
                )

            # trap: must never fall back to a plaintext env var
            os.environ["PG_PASSWORD"] = "should-never-be-read"
            os.environ.pop("PG_PASSWORD_FILE", None)
            try:
                bad = load_secret("pg_password")
            except Exception:
                pass
            else:
                not_passed(
                    f"load_secret('pg_password') returned {bad!r} with no PG_PASSWORD_FILE set -- "
                    f"it must fail loudly, not silently fall back to a plaintext PG_PASSWORD env var"
                )

            # missing file
            os.environ.pop("PG_PASSWORD", None)
            os.environ["PG_PASSWORD_FILE"] = str(Path(tmp) / "does-not-exist")
            try:
                bad2 = load_secret("pg_password")
            except Exception:
                pass
            else:
                not_passed(
                    f"load_secret('pg_password') returned {bad2!r} when PG_PASSWORD_FILE pointed "
                    f"at a missing file -- it must raise, not return a default"
                )
    finally:
        os.environ.clear()
        os.environ.update(old_env)

    return "loader reads the file mount and fails loudly when the env var/file is absent"


@guarded
def main():
    detail_a = _run_half_a()
    detail_compose = _check_compose_structure()
    detail_loader = _check_loader()
    passed(f"{detail_a}; {detail_compose}; {detail_loader}")


if __name__ == "__main__":
    main()
