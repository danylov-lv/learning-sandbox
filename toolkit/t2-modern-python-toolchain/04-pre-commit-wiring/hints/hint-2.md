# Hint 2

A `.pre-commit-config.yaml` is a list under `repos:`, each entry a
`repo:` URL + a `rev:` + a `hooks:` list, each hook identified by its
`id:` as defined by that repo's own `.pre-commit-hooks.yaml`. You don't
invent hook ids — you look them up in the tool's repo:

- `astral-sh/ruff-pre-commit` defines two hook ids: one for linting,
  one for formatting.
- `pre-commit/mirrors-mypy` defines one hook id, and it accepts
  extra CLI flags via `args:` — the same flag you passed directly to
  `mypy` in task 03.
- `pre-commit/pre-commit-hooks` is a grab-bag repo with many hook ids;
  you only need two of them here, both named for what they do.

Try your config locally before trusting the validator: `cd` into a
throwaway git repo of your own with a copy of one fixture, and run
`pre-commit run --all-files` yourself.
