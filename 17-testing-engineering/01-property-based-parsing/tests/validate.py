import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))
sys.path.insert(0, str(TASK_ROOT))

from harness.mutation import grade  # noqa: E402

if __name__ == "__main__":
    grade(
        test_paths=["tests/test_parser.py"],
        correct_impl=str(TASK_ROOT / "src" / "impl.py"),
        mutant_dir=str(MODULE_ROOT / ".authoring" / "mutants" / TASK_ROOT.name),
        cwd=str(TASK_ROOT),
        min_tests=4,
    )
