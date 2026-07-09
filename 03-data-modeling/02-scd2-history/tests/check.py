"""Thin runner: delegates to harness/validate.py --task 02."""

import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MODULE_ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))


def main():
    result = subprocess.run(
        ["uv", "run", "python", "harness/validate.py", "--task", "02"],
        cwd=MODULE_ROOT,
    )
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
