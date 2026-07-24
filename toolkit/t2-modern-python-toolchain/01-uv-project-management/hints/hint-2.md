# Hint 2

Three separate `pyproject.toml` tables need attention:

- `[project]` `dependencies` — a plain list of PEP 508 requirement
  strings. What does `cli.py` `import`, and which PyPI distribution
  provides it?
- `[project.scripts]` — a table mapping a command name to
  `"module.submodule:function"`. The validator expects the command to be
  named exactly `pricetool`.
- `[dependency-groups]` — PEP 735 syntax, a table of named lists, each a
  list of requirement strings, sibling to `[project]` (not nested inside
  it). `uv sync` installs the `dev` group by default alongside your
  regular dependencies.

After editing, `uv sync` regenerates `project/uv.lock` for you — don't
write it by hand, and don't worry that it doesn't exist yet.
