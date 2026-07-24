# Hint 1

Run `uv run pricetool` right now, before changing anything, and read the
error. Then run `uv run python -c "import pricetool.cli"` and read *that*
error too — they're not the same failure, and both point at something
missing from `pyproject.toml`.

Separately: `project/tests/test_cli.py` exists but nothing installs
`pytest` for this project yet. That's a second, independent gap from the
runtime one.
