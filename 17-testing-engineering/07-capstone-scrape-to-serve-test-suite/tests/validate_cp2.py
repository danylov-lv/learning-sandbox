"""CP2 -- integration (repo+cache) and contract (API) tests. Needs Docker.

Container startup (Postgres + Redis) happens once per `python -m pytest`
subprocess this spawns (session-scoped fixtures), but `grade()` spawns one
such subprocess per mutant plus one for the correct-impl baseline, so the
per-mutant timeout is generous to give room for a cold image pull/start on
a slow machine.
"""

import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))
sys.path.insert(0, str(TASK_ROOT))

from harness.mutation import grade  # noqa: E402

if __name__ == "__main__":
    grade(
        test_paths=["tests/test_integration.py", "tests/test_contract.py"],
        correct_impl=str(TASK_ROOT / "src" / "impl.py"),
        mutant_dir=str(MODULE_ROOT / ".authoring" / "mutants" / TASK_ROOT.name / "cp2"),
        cwd=str(TASK_ROOT),
        min_tests=5,
        timeout=300,
    )
