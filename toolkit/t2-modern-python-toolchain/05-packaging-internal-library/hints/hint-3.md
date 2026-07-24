# Hint 3

Shape (the version value below is illustrative — copy the real one out of
`src/pricelib/__init__.py`, don't reuse this literal):

```toml
[project]
name = "pricelib"
description = "Internal price-summary library."
version = "<match __version__ exactly>"
requires-python = ">=3.11"
dependencies = []

[project.scripts]
pricelib = "pricelib.cli:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/pricelib"]
```

Once `uv build` produces `dist/*.whl` and `dist/*.tar.gz`, prove it
actually works installed (not just built) — in a scratch venv:
`uv venv /tmp/pkgcheck && uv pip install --python /tmp/pkgcheck dist/*.whl`,
then run the installed `pricelib` command from that venv directly
(its `Scripts/`/`bin/` directory), not via `uv run`.
