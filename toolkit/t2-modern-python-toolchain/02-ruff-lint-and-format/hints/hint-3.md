# Hint 3

Config shape (fill in the real rule codes yourself — don't just copy
this, the validator checks the actual prefixes and the actual
per-file-ignores key):

```toml
[tool.ruff]
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "<isort-family>", "<bugbear-family>"]

[tool.ruff.lint.per-file-ignores]
"__init__.py" = ["F401"]
```

For `report.py`, work through `ruff check` one violation at a time —
after each real fix, re-run `ruff check` and watch the count drop. When
`ruff check` is clean, run `ruff format project/src` once and then
`ruff format --check project/src` should also report clean. Do not add
`# noqa` anywhere — the validator caps it at zero.
