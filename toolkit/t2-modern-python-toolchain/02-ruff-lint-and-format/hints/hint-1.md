# Hint 1

Run `ruff check project/src` and `ruff format --check project/src` right
now, before changing anything, from inside `project/`. Read what ruff
already catches with the stock config — then read `report.py` and
`__init__.py` yourself and see if you can spot anything ruff *isn't*
catching yet. That gap is what the config is missing.
