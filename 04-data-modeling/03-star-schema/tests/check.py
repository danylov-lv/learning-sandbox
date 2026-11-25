import os
import subprocess
import sys

MODULE_ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))

if __name__ == "__main__":
    result = subprocess.run(
        ["uv", "run", "python", "harness/validate.py", "--task", "03"],
        cwd=MODULE_ROOT,
    )
    sys.exit(result.returncode)
