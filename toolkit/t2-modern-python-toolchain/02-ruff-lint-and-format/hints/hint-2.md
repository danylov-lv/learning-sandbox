# Hint 2

Ruff's rule config lives under `[tool.ruff.lint]` in modern ruff (the
flat `[tool.ruff]` schema for `select`/`ignore` still works but is
deprecated). Three keys matter here: `select` (a list of rule codes or
prefixes — a prefix like `"B"` means "every B-rule"), and
`per-file-ignores` (a table mapping a filename pattern to a list of codes
exempted *only* for files matching that pattern).

`summarize`'s default argument and the import block's order are not
things `E`/`F` catch — look up which ruff rule *family* (a letter
prefix) covers "mutable default argument" and which covers "import
sorting."

For `__init__.py`, don't touch `select`/`ignore` to make F401 go away
globally — that would also hide a real unused import somewhere else. Use
`per-file-ignores` scoped to that one filename.
