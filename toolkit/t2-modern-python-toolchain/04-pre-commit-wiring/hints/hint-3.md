# Hint 3

Skeleton (fill in the real `rev:` for each repo yourself — pick the
latest stable tag at the time you do this; the validator doesn't check
which version, only that hooks are wired and pinned):

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: <tag>
    hooks:
      - id: ruff
      - id: ruff-format

  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: <tag>
    hooks:
      - id: mypy
        args: [--strict]

  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: <tag>
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
```

Save this as `.pre-commit-config.yaml` directly in this task directory
(next to `README.md`), not inside `fixtures/`.
