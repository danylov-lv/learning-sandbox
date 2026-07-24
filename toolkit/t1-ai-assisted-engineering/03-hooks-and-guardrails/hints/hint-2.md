For `run-tests.py`: the project root to test is either
`os.environ.get("CLAUDE_PROJECT_DIR")` or the `cwd` field from the JSON
payload -- prefer the env var if it's set, since that's the value Claude
Code itself guarantees is the actual project root regardless of where the
hook process's own cwd ends up. Run tests with
`subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=project_dir,
capture_output=True, text=True)` -- no path arguments needed, since every
fixture project here has its tests under a `tests/` directory that
pytest's default discovery finds on its own from that cwd.

For `lint.py`: same project-root resolution, but the command is just
`["ruff", "check"]` (a real installed CLI tool on PATH in this
environment -- not invoked through Python) run with the same `cwd=`.

For both: check the subprocess's `returncode`. On non-zero, print
`json.dumps({"decision": "block", "reason": "..."})` to stdout and still
exit 0 -- printing to stdout and then exiting non-zero at the same time
is not wrong exactly, but the point of the JSON path is that it's the
one Claude Code actually reads as structured feedback rather than a raw
error dump. On success, don't print a decision object at all (empty
stdout, or nothing that parses as `{"decision": "block", ...}`), and
exit 0.
