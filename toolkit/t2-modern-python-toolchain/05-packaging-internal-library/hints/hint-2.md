# Hint 2

Three separate additions to `project/pyproject.toml`:

- `[build-system]` — a `requires` list (what's needed to build) and a
  `build-backend` string (which backend does the building). Task 01's
  given project already has a correct one of these you can look at as a
  reference for the shape — this task is about knowing you need it and
  writing it here.
- `[project]` `version` — a plain string, sibling to `name` and
  `description`. Read `src/pricelib/__init__.py` for the exact value it
  must match.
- `[project.scripts]` — same table shape you used in task 01: a command
  name mapped to `"package.module:function"`.

After that, `uv build` should produce a `.whl` and a `.tar.gz` under
`dist/`.
