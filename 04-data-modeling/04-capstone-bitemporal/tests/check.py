import os
import re
import subprocess
import sys

TASK_ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
MODULE_ROOT = os.path.normpath(os.path.join(TASK_ROOT, ".."))
DESIGN_PATH = os.path.join(TASK_ROOT, "DESIGN.md")

MIN_CONTENT_CHARS = 1500

if __name__ == "__main__":
    if not os.path.exists(DESIGN_PATH):
        print("NOT PASSED: DESIGN.md still looks like the empty template")
        sys.exit(1)

    with open(DESIGN_PATH, encoding="utf-8") as f:
        text = f.read()

    non_heading = "\n".join(
        line for line in text.splitlines() if not line.strip().startswith("#")
    )
    non_heading = re.sub(r"\s+", " ", non_heading).strip()

    if len(non_heading) < MIN_CONTENT_CHARS:
        print("NOT PASSED: DESIGN.md still looks like the empty template")
        sys.exit(1)

    result = subprocess.run(
        ["uv", "run", "python", "harness/validate.py", "--all"],
        cwd=MODULE_ROOT,
    )
    sys.exit(result.returncode)
