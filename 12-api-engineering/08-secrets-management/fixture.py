"""s12.t08 -- deterministic builder for the "find the leaked secret" fixture.

THIS FILE IS THE ANSWER KEY. It knows every secret it plants, on purpose --
`tests/validate.py` needs that to grade recall/precision independently of
whatever the learner's scanner returns. Reading this file (or
tests/validate.py) before finishing HALF A is exactly like reading
`.authoring/design.md` before finishing a task: it spoils the exercise. See
the README's "Off-limits" section.

`build_leaky_repo()` materializes a small, throwaway, REAL git repository
(`git init` + several commits with plausible messages) at `leaky-repo/`
(gitignored -- see the module .gitignore) simulating a notification
microservice's repo history. It plants 6 classes of leaked secret across the
tree and history, including one that was committed and later "removed" in a
later commit (present only in `git log -p`/`git show`, absent from the
working tree), plus 4 realistic decoys that must NOT be reported. Everything
is derived from a fixed seed via stdlib `random` -- rerun this and every
planted value, every commit message, and (since commit dates/authors are
also fixed) every commit sha comes out byte-identical.

Run standalone to (re)build the fixture for manual poking:

    uv run python fixture.py

`tests/validate.py` imports `build_leaky_repo` directly instead (no import-
time side effects -- nothing runs until you call it).
"""

import base64
import json
import os
import random
import shutil
import stat
import string
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parent
DEFAULT_REPO_DIR = TASK_ROOT / "leaky-repo"

# Local seed for this task's own fixture -- independent of the module's
# shared `shop` corpus seed (harness.common.SEED); this fixture never
# touches Postgres/Redis at all.
FIXTURE_SEED = 190804

_ALPHABETS = {
    "hex": "0123456789abcdef",
    "alnum": string.ascii_letters + string.digits,
    "upper_alnum": string.ascii_uppercase + string.digits,
}


def _rand_token(rng, alphabet_name, n):
    alphabet = _ALPHABETS[alphabet_name]
    return "".join(rng.choice(alphabet) for _ in range(n))


def _write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def _force_rmtree(path):
    """shutil.rmtree that survives Windows marking git object files
    read-only (git writes loose objects/packs as 0o444)."""

    def _on_rm_error(func, p, exc_info):
        try:
            os.chmod(p, stat.S_IWRITE)
        except OSError:
            pass
        func(p)

    shutil.rmtree(path, onerror=_on_rm_error)


def _run_git(args, cwd, env=None):
    result = subprocess.run(
        ["git", *args], cwd=str(cwd), capture_output=True, text=True, env=env
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed (exit {result.returncode}): {result.stderr.strip()}"
        )
    return result.stdout.strip()


def _commit(dest, message, when, base_env):
    """Stage everything and commit with fixed author/committer identity and
    timestamp, so the resulting commit (and its sha) is fully deterministic.
    Returns the new commit's sha."""
    env = dict(base_env)
    ts = when.strftime("%Y-%m-%dT%H:%M:%S+00:00")
    env.update(
        {
            "GIT_AUTHOR_NAME": "Ops Bot",
            "GIT_AUTHOR_EMAIL": "ops-bot@notify-svc.example.com",
            "GIT_AUTHOR_DATE": ts,
            "GIT_COMMITTER_NAME": "Ops Bot",
            "GIT_COMMITTER_EMAIL": "ops-bot@notify-svc.example.com",
            "GIT_COMMITTER_DATE": ts,
        }
    )
    _run_git(["-c", "core.autocrlf=false", "add", "-A"], cwd=dest, env=env)
    _run_git(
        ["-c", "commit.gpgsign=false", "-c", "core.autocrlf=false", "commit", "-q", "-m", message],
        cwd=dest,
        env=env,
    )
    return _run_git(["rev-parse", "HEAD"], cwd=dest, env=env)


def _fake_pem_block(raw_bytes, label):
    """A syntactically PEM-shaped block from random bytes -- NOT a real,
    parseable cryptographic key (no ASN.1 structure underneath the base64),
    so it can never be mistaken for a working credential. Realistic enough
    for a textual leak-detection exercise, which is all this task asks."""
    b64 = base64.b64encode(raw_bytes).decode("ascii")
    lines = [b64[i : i + 64] for i in range(0, len(b64), 64)]
    body = "\n".join(lines)
    return f"-----BEGIN {label}-----\n{body}\n-----END {label}-----\n"


def _fake_ssh_pubkey(raw_bytes):
    b64 = base64.b64encode(raw_bytes).decode("ascii")
    return f"ssh-rsa {b64} deploy@notify-svc.example.com\n"


def _notebook_json(access_key, secret_key):
    """A minimal, valid nbformat-4 notebook: a markdown cell plus a code
    cell whose STORED OUTPUT (not the source) has printed AWS-looking
    credentials -- the classic "debugged locally, forgot the output cell
    still has the printout" leak. A plain-text scan of the .ipynb file (it's
    just JSON) finds this the same way it would find it in a .log file."""
    notebook = {
        "cells": [
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": [
                    "# Debug: duplicate notification investigation\n",
                    "\n",
                    "Scratch notebook while chasing the double-send bug on the order-backfill job.",
                ],
            },
            {
                "cell_type": "code",
                "execution_count": 3,
                "metadata": {},
                "outputs": [
                    {
                        "name": "stdout",
                        "output_type": "stream",
                        "text": [
                            "session credentials (local only, for the backfill script):\n",
                            f"AWS_ACCESS_KEY_ID={access_key}\n",
                            f"AWS_SECRET_ACCESS_KEY={secret_key}\n",
                        ],
                    }
                ],
                "source": [
                    "import boto3\n",
                    "session = boto3.Session()\n",
                    "creds = session.get_credentials().get_frozen_credentials()\n",
                    'print(f"AWS_ACCESS_KEY_ID={creds.access_key}")\n',
                    'print(f"AWS_SECRET_ACCESS_KEY={creds.secret_key}")\n',
                ],
            },
        ],
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python", "version": "3.11"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    return json.dumps(notebook, indent=1) + "\n"


README_TEMPLATE = """# notify-svc

Notification delivery microservice for the marketplace platform: consumes
order/shipment events and fans them out to email/SMS/push providers.

## Configuration

Configuration is environment-driven -- see `.env.example` for the full list
of variables `notify-svc` reads at startup.

This service does not talk to AWS directly, but for engineers coming from
our other services: AWS's own documentation uses a placeholder access key
that looks like `AKIAIOSFODNN7EXAMPLE` in every code sample. That string is
AWS's published example key, not a real credential -- it is safe to see it
in docs or screenshots.

## Development

    pip install -r requirements.txt
    uvicorn src.main:app --reload

See `docker-compose.yml` for the local stack.
"""

CHANGELOG_TEMPLATE = """# Changelog

## v0.4.0 - 2025-02-18
- Fixed a duplicate-notification bug on retrying failed sends
  (build a3f9c21e7b4d0f8823a1c9e4f6b7d2c1)

## v0.3.0 - 2025-01-20
- Added CI deploy workflow

## v0.1.0 - 2025-01-06
- Initial scaffold
"""

REQUIREMENTS_TEMPLATE = """fastapi>=0.115
uvicorn[standard]>=0.32
psycopg[binary]>=3.2
boto3>=1.34
pyyaml>=6
"""

GITIGNORE_C1 = "__pycache__/\n*.pyc\n.venv/\n"

MAIN_PY_TEMPLATE = '''"""notify-svc -- notification delivery service (skeleton)."""

from fastapi import FastAPI

app = FastAPI(title="notify-svc")


@app.get("/health")
def health():
    return {"status": "ok"}
'''

ENV_TEMPLATE = (
    "# Local development environment -- DO NOT COMMIT\n"
    "NOTIFY_ENV=development\n"
    "PG_HOST=localhost\n"
    "PG_PORT=5432\n"
    "PG_USER=notify_svc\n"
    "PG_PASSWORD={pg_password}\n"
    "PG_DB=notify\n"
)

ENV_EXAMPLE_TEMPLATE = (
    "# Copy to .env and fill in real values for local development.\n"
    "NOTIFY_ENV=development\n"
    "PG_HOST=localhost\n"
    "PG_PORT=5432\n"
    "PG_USER=notify_svc\n"
    "PG_PASSWORD=\n"
    "PG_DB=notify\n"
)

CONFIG_PY_TEMPLATE = (
    '"""Database connection settings for notify-svc.\n'
    "\n"
    "TODO(JIRA-4821): move this to env-based config before GA.\n"
    '"""\n'
    "\n"
    'DATABASE_URL = "postgresql://notify_svc:{dsn_token}@db.internal.notify.example.com:5432/notify"\n'
    "\n"
    "\n"
    "def get_database_url() -> str:\n"
    "    return DATABASE_URL\n"
)

COMPOSE_TEMPLATE = (
    "services:\n"
    "  api:\n"
    "    image: notify-svc-api:latest\n"
    "    environment:\n"
    '      JWT_SIGNING_KEY: "{signing_key}"\n'
    "      PG_HOST: postgres\n"
    '      PG_PORT: "5432"\n'
    "    ports:\n"
    '      - "8080:8080"\n'
    "    depends_on:\n"
    "      - postgres\n"
    "\n"
    "  postgres:\n"
    "    image: postgres:16\n"
    "    environment:\n"
    "      POSTGRES_DB: notify\n"
    "      POSTGRES_USER: notify_svc\n"
)

# Plain string (NOT an f-string/`.format()` target) -- GitHub Actions'
# `${{ github.sha }}` syntax would collide with str.format()'s own brace
# escaping. The token is spliced in via a plain .replace() below instead.
DEPLOY_WORKFLOW_TEMPLATE = """name: Deploy

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Push image
        env:
          REGISTRY_TOKEN: "__REGISTRY_TOKEN__"
        run: |
          echo "$REGISTRY_TOKEN" | docker login registry.notify.example.com -u ci --password-stdin
          docker build -t registry.notify.example.com/notify-svc:${{ github.sha }} .
          docker push registry.notify.example.com/notify-svc:${{ github.sha }}
"""


def build_leaky_repo(dest=None, *, force=True):
    """Materialize the deterministic leaky repo at `dest` (default:
    ./leaky-repo/ next to this file). Returns a manifest:

        {
          "repo_dir": str,
          "secrets": [
            {"id": str, "class": str, "path": str, "source": "worktree"|"history",
             "commit": str | None, "valid_commits": list[str] | None, "value": str | None},
            ...  # 6 entries
          ],
          "decoys": [{"id": str, "path": str}, ...]  # 4 entries
        }

    `secrets[i]["value"]` is the exact leaked substring a correct scanner
    should surface for that class (None for the private-key file, where the
    file's mere presence/PEM header is the signal, not a specific token).
    `secrets[i]["commit"]`/`["valid_commits"]` are populated only for the one
    secret whose ONLY trace is in git history (the committed-then-removed
    .env): the file rides along unchanged in every commit's tree from the
    one that added it through the one just before it was removed (commits
    are cumulative snapshots), so any sha in `valid_commits` legitimately
    recovers it -- `commit` alone is just the first (add) commit, kept for
    readable error messages.

    Deterministic: every token, every commit message/date/author, and (as a
    consequence) every commit sha is reproducible byte-for-byte given
    FIXTURE_SEED -- rerunning this produces an identical manifest.
    """
    dest = Path(dest) if dest is not None else DEFAULT_REPO_DIR
    if dest.exists():
        if not force:
            raise FileExistsError(f"{dest} already exists (pass force=True to rebuild)")
        _force_rmtree(dest)
    dest.mkdir(parents=True, exist_ok=True)

    # --- deterministic token draws, FIXED order -- do not reorder ---
    rng = random.Random(FIXTURE_SEED)
    env_pw_token = _rand_token(rng, "hex", 24)
    dsn_token = _rand_token(rng, "alnum", 24)
    compose_signing_token = _rand_token(rng, "hex", 32)
    aws_access_key = "AKIA" + _rand_token(rng, "upper_alnum", 16)
    aws_secret_key = _rand_token(rng, "alnum", 40)
    ci_token = "ghp_" + _rand_token(rng, "alnum", 36)
    private_key_bytes = bytes(rng.getrandbits(8) for _ in range(800))
    public_key_bytes = bytes(rng.getrandbits(8) for _ in range(200))

    base_env = dict(os.environ)
    when = datetime(2025, 1, 6, 9, 15, 0, tzinfo=timezone.utc)
    step = timedelta(days=3)

    _run_git(["init", "-q", "-b", "main"], cwd=dest)

    # C1 -- initial scaffold (also plants decoys D1 README AWS-example-key
    # and D4 CHANGELOG hash, both present from the very first commit)
    _write(dest / "README.md", README_TEMPLATE)
    _write(dest / "CHANGELOG.md", CHANGELOG_TEMPLATE)
    _write(dest / "requirements.txt", REQUIREMENTS_TEMPLATE)
    _write(dest / ".gitignore", GITIGNORE_C1)
    _write(dest / "src" / "__init__.py", '"""notify-svc package."""\n')
    _write(dest / "src" / "main.py", MAIN_PY_TEMPLATE)
    _commit(dest, "Initial scaffold: notify-svc skeleton", when, base_env)
    when += step

    # C2 -- committed .env (later removed -- the HISTORY-ONLY secret). It
    # rides along, byte-unchanged, in every commit's tree from here through
    # C7 (git commits are cumulative snapshots -- a file untouched by a
    # later commit is still part of that commit's tree). ANY of those shas
    # is a legitimately correct answer for "which commit can I recover this
    # from", so we track all of them, not just the one that added it.
    _write(dest / ".env", ENV_TEMPLATE.format(pg_password=env_pw_token))
    env_present_shas = [_commit(dest, "Add local dev environment config", when, base_env)]
    when += step

    # C3 -- hardcoded DSN in source
    _write(dest / "src" / "config.py", CONFIG_PY_TEMPLATE.format(dsn_token=dsn_token))
    env_present_shas.append(_commit(dest, "Wire up Postgres connection in config", when, base_env))
    when += step

    # C4 -- signing key inline in compose
    _write(dest / "docker-compose.yml", COMPOSE_TEMPLATE.format(signing_key=compose_signing_token))
    env_present_shas.append(_commit(dest, "Add docker-compose for local stack", when, base_env))
    when += step

    # C5 -- cloud-looking access key leaked via a debug notebook's output
    _write(dest / "notebooks" / "debug_query.ipynb", _notebook_json(aws_access_key, aws_secret_key))
    env_present_shas.append(
        _commit(dest, "Add debug notebook for order-backfill investigation", when, base_env)
    )
    when += step

    # C6 -- private key file (real leak) + its public counterpart (decoy D3)
    _write(dest / "deploy" / "deploy_key.pem", _fake_pem_block(private_key_bytes, "RSA PRIVATE KEY"))
    _write(dest / "deploy" / "deploy_key.pub", _fake_ssh_pubkey(public_key_bytes))
    env_present_shas.append(_commit(dest, "Add deploy key for CI artifact upload", when, base_env))
    when += step

    # C7 -- token in CI config
    _write(
        dest / ".github" / "workflows" / "deploy.yml",
        DEPLOY_WORKFLOW_TEMPLATE.replace("__REGISTRY_TOKEN__", ci_token),
    )
    env_present_shas.append(_commit(dest, "CI: add deploy workflow", when, base_env))
    when += step

    # C8 -- security cleanup: remove .env from the working tree (it stays
    # in commit C2's history forever), add .env.example (decoy D2)
    (dest / ".env").unlink()
    _write(dest / ".env.example", ENV_EXAMPLE_TEMPLATE)
    _write(dest / ".gitignore", GITIGNORE_C1 + "\n.env\n")
    _commit(dest, "Security cleanup: remove committed .env, add example template", when, base_env)

    secrets = [
        {
            "id": "env_password",
            "class": "committed_env_file (history-only)",
            "path": ".env",
            "source": "history",
            "commit": env_present_shas[0],  # the commit that introduced it
            "valid_commits": env_present_shas,  # any of these correctly recovers it
            "value": env_pw_token,
        },
        {
            "id": "hardcoded_dsn",
            "class": "hardcoded_dsn_in_source",
            "path": "src/config.py",
            "source": "worktree",
            "commit": None,
            "value": dsn_token,
        },
        {
            "id": "compose_signing_key",
            "class": "signing_key_in_compose",
            "path": "docker-compose.yml",
            "source": "worktree",
            "commit": None,
            "value": compose_signing_token,
        },
        {
            "id": "notebook_cloud_key",
            "class": "cloud_access_key_in_notebook",
            "path": "notebooks/debug_query.ipynb",
            "source": "worktree",
            "commit": None,
            "value": aws_access_key,
        },
        {
            "id": "deploy_private_key",
            "class": "private_key_file",
            "path": "deploy/deploy_key.pem",
            "source": "worktree",
            "commit": None,
            "value": None,  # graded by path + a "PRIVATE KEY" marker in the reported value
        },
        {
            "id": "ci_deploy_token",
            "class": "token_in_ci_config",
            "path": ".github/workflows/deploy.yml",
            "source": "worktree",
            "commit": None,
            "value": ci_token,
        },
    ]
    decoys = [
        {"id": "aws_example_key", "path": "README.md"},
        {"id": "env_example_template", "path": ".env.example"},
        {"id": "deploy_public_key", "path": "deploy/deploy_key.pub"},
        {"id": "changelog_hash", "path": "CHANGELOG.md"},
    ]
    return {"repo_dir": str(dest), "secrets": secrets, "decoys": decoys}


if __name__ == "__main__":
    manifest = build_leaky_repo()
    print(f"built leaky-repo at {manifest['repo_dir']}")
    print(f"{len(manifest['secrets'])} planted secrets, {len(manifest['decoys'])} decoys")
