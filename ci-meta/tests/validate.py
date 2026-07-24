"""Validator for ci-meta itself.

Unlike every other module's validate.py in this repo, this one PASSES on
stock: ci-meta is committed CI infrastructure, not a learner exercise with
an unsolved stub, so there is nothing here that is *supposed* to be
failing. See ci-meta/README.md for why ci-meta is the one exception to
the repo's "every validator fails by design" rule.

Stdlib only.
"""

from __future__ import annotations

import importlib
import re
import sys
from pathlib import Path

CI_META_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = CI_META_DIR.parent

sys.path.insert(0, str(CI_META_DIR))


def check_modules_import() -> None:
    for modname in ("registry", "checks", "detect_changes", "run_module_ci", "repo_guards"):
        importlib.import_module(modname)


def check_registry_paths_exist() -> None:
    import registry

    missing = [
        mid for mid, m in registry.MODULES.items()
        if not (REPO_ROOT / m.path).is_dir()
    ]
    if missing:
        raise AssertionError(f"registry paths missing on disk: {missing}")


def check_registry_matches_real_dirs() -> None:
    import registry

    task_dir_re = re.compile(r"^\d{2}-")
    toolkit_dir_re = re.compile(r"^t\d+-")

    real: set[str] = set()
    for entry in REPO_ROOT.iterdir():
        if not entry.is_dir():
            continue
        if entry.name == "toolkit":
            for sub in entry.iterdir():
                if sub.is_dir() and toolkit_dir_re.match(sub.name):
                    real.add(f"toolkit/{sub.name}")
        elif task_dir_re.match(entry.name):
            real.add(entry.name)

    registered = set(registry.all_module_ids())
    if real != registered:
        raise AssertionError(
            f"registry/disk mismatch -- on disk not registered: "
            f"{sorted(real - registered)}; registered but missing on disk: "
            f"{sorted(registered - real)}"
        )


def check_detect_changes_mapping() -> None:
    import detect_changes

    cases = {
        "02-sql-optimization/foo.sql": ["02-sql-optimization"],
        "toolkit/t3-cli-data-toolkit/x": ["toolkit/t3-cli-data-toolkit"],
        "README.md": [],
        "18-rust-track/01-log-parser-aggregations/src/lib.rs": ["18-rust-track"],
        "ci-meta/registry.py": [],
        ".github/workflows/ci.yml": [],
        "20-kubernetes/cluster/kind-config.yaml": ["20-kubernetes"],
    }
    for path, expected in cases.items():
        got = detect_changes.map_files_to_modules([path])
        if got != expected:
            raise AssertionError(f"map_files_to_modules({path!r}) = {got}, expected {expected}")

    # A change under both a longer and a shorter prefix must resolve to the
    # longer (more specific) match, and multiple files must dedupe + preserve
    # registry order regardless of input order.
    mixed = [
        "toolkit/t4-git-advanced/01-interactive-rebase-cleanup/README.md",
        "01-sql-foundations/README.md",
        "toolkit/t4-git-advanced/02-bisect-find-regression/README.md",
    ]
    got = detect_changes.map_files_to_modules(mixed)
    expected = ["01-sql-foundations", "toolkit/t4-git-advanced"]
    if got != expected:
        raise AssertionError(f"map_files_to_modules(mixed) = {got}, expected {expected}")


def check_workflow_file() -> None:
    workflow = REPO_ROOT / ".github" / "workflows" / "ci.yml"
    if not workflow.is_file():
        raise AssertionError(".github/workflows/ci.yml not found")

    text = workflow.read_text(encoding="utf-8")

    try:
        import yaml  # type: ignore
    except ImportError:
        yaml = None

    if yaml is not None:
        doc = yaml.safe_load(text)
        jobs = doc.get("jobs", {})
        for job in ("detect", "verify", "guards"):
            if job not in jobs:
                raise AssertionError(f"workflow missing job: {job}")

    required_substrings = (
        "detect_changes.py",
        "run_module_ci.py",
        "repo_guards.py",
        "fromJSON(needs.detect.outputs.modules)",
    )
    for s in required_substrings:
        if s not in text:
            raise AssertionError(f"workflow does not reference: {s}")


CHECKS = (
    check_modules_import,
    check_registry_paths_exist,
    check_registry_matches_real_dirs,
    check_detect_changes_mapping,
    check_workflow_file,
)


def main() -> int:
    for check in CHECKS:
        check()
    print("PASSED")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"NOT PASSED: {exc}")
        sys.exit(1)
