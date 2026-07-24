# Hint 3

Shape of what's needed (fill in the real values yourself — don't just
copy this skeleton verbatim, the validator checks the actual dependency
name and version-less script target):

```toml
[project]
dependencies = [
    "<pypi-name-of-the-yaml-package>>=6",
]

[project.scripts]
pricetool = "pricetool.cli:main"

[dependency-groups]
dev = [
    "pytest>=8",
]
```

Once that's in place: `uv sync`, then `uv run pricetool` should print a
`count=... min=... max=... avg=... currency=...` line, `uv run pytest -q`
should pass, and `uv tool run --from . pricetool` (run from inside
`project/`) should print the same summary line as `uv run pricetool` —
built and installed into a throwaway tool environment instead of your
project's own `.venv`.
